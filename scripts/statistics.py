#!/usr/bin/env python3
"""Prints a quick file/line/size summary of this repository's files,
broken down by top-level directory (backend, scraper, doc, storage, ...)
and by file type.

Every file is counted and sorted into a category by its extension (see
_EXTENSIONS below): source, docs, config, data, media, office, other.
Lines are counted only for text files - binary ones (PDFs, databases,
images, ...) add to the file count and size but show "-" for lines. An
extension the table doesn't know counts as text if its first 8 KB hold no
NUL byte.

Two tables are printed:
- by directory: one line per top-level directory, with one indented
  sub-line per category inside it;
- by type: one line per category + extension across the whole scan.

Files come from a disk walk that skips the virtual environment, VCS
metadata and tool caches (see _EXCLUDED_DIRS), since those would dwarf the
real numbers and aren't "this project's files" in any useful sense - or,
with --tracked, from `git ls-files`, which also honors .gitignore.

Usage (run from anywhere - the scan root is resolved from this script's own
location, not the current working directory):

    python scripts/statistics.py
    scripts\\statistics.bat                         (Windows wrapper, see that file)
    python scripts/statistics.py --path backend     (scan a subtree instead)
    python scripts/statistics.py --ext py           (only .py files - the old report)
    python scripts/statistics.py --category source,docs --by dir
    python scripts/statistics.py --exclude storage --tracked
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directory names that hold generated/vendored content rather than this
# project's own files - matched against every path component, so a nested
# occurrence (e.g. backend/app/__pycache__) is excluded too, not just one
# at the repo root.
_EXCLUDED_DIRS = {".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}

# Report order of the categories.
CATEGORIES = ("source", "docs", "config", "data", "media", "office", "other")

# Extension (lower case, no dot) -> (category, is_text). A dotfile with no
# other extension is looked up by its name without the dot (".gitignore"
# -> "gitignore").
_EXTENSIONS: dict[str, tuple[str, bool]] = {
    **{
        ext: ("source", True)
        for ext in ("py", "js", "ts", "html", "htm", "css", "bat", "cmd", "ps1", "sh", "mako", "sql")
    },
    **{ext: ("docs", True) for ext in ("md", "txt", "rst")},
    **{
        ext: ("config", True)
        for ext in (
            "json",
            "yaml",
            "yml",
            "toml",
            "ini",
            "cfg",
            "example",
            "gitignore",
            "gitkeep",
            "gitattributes",
            "env",
        )
    },
    **{ext: ("data", False) for ext in ("db", "sqlite", "sqlite3", "pdf")},
    "csv": ("data", True),
    **{ext: ("media", False) for ext in ("jpg", "jpeg", "png", "gif", "webp", "ico", "mp4", "webm", "thumbnail")},
    "svg": ("media", True),
    "drawio": ("media", True),
    **{ext: ("office", False) for ext in ("pptx", "docx", "xlsx", "odt", "ods", "odp")},
}

_SNIFF_BYTES = 8192
NO_EXTENSION = "(none)"


@dataclass
class Stats:
    """File/line/size counts accumulated for one row of the report.

    `lines` sums the text files only; `text_files` says how many there
    were, so a row of binary files alone can show "-" instead of 0.
    """

    files: int = 0
    text_files: int = 0
    lines: int = 0
    size_bytes: int = 0

    def add(self, other: Stats) -> None:
        self.files += other.files
        self.text_files += other.text_files
        self.lines += other.lines
        self.size_bytes += other.size_bytes


# (top-level group, category, extension) -> counts.
StatsKey = tuple[str, str, str]


def format_size(size_bytes: int) -> str:
    """Args:
        size_bytes: A byte count, e.g. `Stats.size_bytes`.

    Returns:
        `size_bytes` formatted as a human-readable string, scaled to B/KB/
        MB/GB (one decimal place from KB up) - whichever unit keeps the
        value under 1024, capping at GB.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size = float(size_bytes)
    for unit in ("KB", "MB", "GB"):
        size /= 1024
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} GB"


def is_excluded(path: Path, root: Path, extra: Iterable[str] = ()) -> bool:
    """Args:
        path: A candidate file's absolute path, somewhere under `root`.
        root: The scan root.
        extra: More directory names to skip (`--exclude`).

    Returns:
        True if any directory component of `path` below `root` names a
        non-source directory (see _EXCLUDED_DIRS) or one of `extra` - i.e.
        the file should not be counted.
    """
    skipped = _EXCLUDED_DIRS | set(extra)
    return any(part in skipped for part in path.relative_to(root).parts[:-1])


def extension(path: Path) -> str:
    """Args:
        path: A file path.

    Returns:
        Its extension in lower case without the dot (`"py"`), a dotfile's
        name without the dot (`".gitignore"` -> `"gitignore"`), or
        `NO_EXTENSION`.
    """
    if path.suffix:
        return path.suffix[1:].lower()
    return path.name[1:].lower() if path.name.startswith(".") else NO_EXTENSION


def looks_like_text(path: Path) -> bool:
    """Args:
        path: A file of unknown type.

    Returns:
        True if its first 8 KB hold no NUL byte (empty files count as text).
    """
    with path.open("rb") as handle:
        return b"\0" not in handle.read(_SNIFF_BYTES)


def classify(path: Path) -> tuple[str, str, bool]:
    """Args:
        path: An existing file.

    Returns:
        `(category, extension, is_text)` - from _EXTENSIONS, or for an
        unknown extension `"other"` with `is_text` sniffed from the content.
    """
    ext = extension(path)
    if ext in _EXTENSIONS:
        category, is_text = _EXTENSIONS[ext]
        return category, ext, is_text
    return "other", ext, looks_like_text(path)


def top_level_group(path: Path, root: Path) -> str:
    """Args:
        path: A candidate file's absolute path, somewhere under `root`.
        root: The scan root `path` was found under.

    Returns:
        `path`'s top-level directory name relative to `root` (e.g.
        `"backend"`, `"scraper"`, `"scripts"`), or `"."` for a file that
        sits directly in `root` with no subdirectory in between.
    """
    relative_parts = path.relative_to(root).parts
    return relative_parts[0] if len(relative_parts) > 1 else "."


def walk_files(root: Path) -> Iterator[Path]:
    """Args:
        root: Directory to scan.

    Yields:
        Every regular file under `root`, recursively (exclusions are
        applied by the caller).
    """
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def tracked_files(root: Path) -> Iterator[Path]:
    """Args:
        root: Directory inside a git work tree.

    Yields:
        The files git tracks under `root` that still exist on disk.

    Raises:
        SystemExit: git isn't installed or `root` isn't in a repository.
    """
    try:
        listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"--tracked needs git and a repository at {root}: {exc}") from None
    for name in listing.decode("utf-8", errors="replace").split("\0"):
        path = root / name
        if name and path.is_file():
            yield path


def collect_stats(
    root: Path,
    files: Iterable[Path] | None = None,
    *,
    exclude: Iterable[str] = (),
    categories: set[str] | None = None,
    extensions: set[str] | None = None,
) -> dict[StatsKey, Stats]:
    """Args:
        root: The scan root.
        files: The files to look at (default: `walk_files(root)`).
        exclude: More directory names to skip, see `is_excluded`.
        categories: Count only these categories (`None` = all).
        extensions: Count only these extensions (`None` = all).

    Returns:
        Counts per (top-level directory, category, extension) for every
        file that isn't excluded or filtered out. Text files that aren't
        valid UTF-8 are still counted, with undecodable bytes ignored
        (`errors="ignore"`).
    """
    exclude = tuple(exclude)
    stats: dict[StatsKey, Stats] = {}
    for path in walk_files(root) if files is None else files:
        if is_excluded(path, root, exclude):
            continue
        category, ext, is_text = classify(path)
        if categories is not None and category not in categories:
            continue
        if extensions is not None and ext not in extensions:
            continue
        entry = stats.setdefault((top_level_group(path, root), category, ext), Stats())
        entry.files += 1
        entry.size_bytes += path.stat().st_size
        if is_text:
            entry.text_files += 1
            entry.lines += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    return stats


def aggregate(stats: dict[StatsKey, Stats], key: Callable[[StatsKey], tuple]) -> dict[tuple, Stats]:
    """Args:
        stats: Result of `collect_stats`.
        key: Picks the part of a `StatsKey` to group by.

    Returns:
        `stats` summed per `key(...)`.
    """
    grouped: dict[tuple, Stats] = {}
    for stats_key, entry in stats.items():
        grouped.setdefault(key(stats_key), Stats()).add(entry)
    return grouped


def directory_rows(stats: dict[StatsKey, Stats]) -> list[tuple[str, Stats]]:
    """Args:
        stats: Result of `collect_stats`.

    Returns:
        `(label, counts)` rows: each top-level directory (by name), followed
        by one indented row per category it contains (in `CATEGORIES` order).
    """
    per_dir = aggregate(stats, lambda k: (k[0],))
    per_dir_category = aggregate(stats, lambda k: (k[0], k[1]))
    rows = []
    for (group,) in sorted(per_dir):
        rows.append((group, per_dir[(group,)]))
        for category in CATEGORIES:
            if (group, category) in per_dir_category:
                rows.append((f"  {category}", per_dir_category[(group, category)]))
    return rows


def type_rows(stats: dict[StatsKey, Stats]) -> list[tuple[str, Stats]]:
    """Args:
        stats: Result of `collect_stats`.

    Returns:
        `(label, counts)` rows, one per category + extension: categories
        in `CATEGORIES` order, extensions within one by size, largest first.
    """
    per_type = aggregate(stats, lambda k: (k[1], k[2]))
    ordered = sorted(per_type.items(), key=lambda item: (CATEGORIES.index(item[0][0]), -item[1].size_bytes, item[0][1]))
    ext_width = max(len(ext) for _, ext in per_type) + 1
    return [
        (f"{category:<7} {('.' + ext if ext != NO_EXTENSION else ext):<{ext_width}}", entry)
        for (category, ext), entry in ordered
    ]


def _lines_text(entry: Stats) -> str:
    return str(entry.lines) if entry.text_files else "-"


def print_table(title: str, rows: list[tuple[str, Stats]]) -> None:
    """Prints `rows` under a `title` header line, followed by a TOTAL of
    the rows that aren't indented (so sub-rows aren't counted twice)."""
    total = Stats()
    for label, entry in rows:
        if not label.startswith(" "):
            total.add(entry)
    all_rows = [*rows, ("TOTAL", total)]
    name_width = max(len(title), *(len(label) for label, _ in all_rows))
    files_width = max(len("files"), *(len(str(entry.files)) for _, entry in all_rows))
    lines_width = max(len("lines"), *(len(_lines_text(entry)) for _, entry in all_rows))
    size_width = max(len("size"), *(len(format_size(entry.size_bytes)) for _, entry in all_rows))

    def line(label: str, files: str, lines: str, size: str) -> str:
        return f"{label:<{name_width}}  {files:>{files_width}}  {lines:>{lines_width}}  {size:>{size_width}}"

    print(line(title, "files", "lines", "size"))
    for label, entry in rows:
        print(line(label, str(entry.files), _lines_text(entry), format_size(entry.size_bytes)))
    print(line("-" * name_width, "-" * files_width, "-" * lines_width, "-" * size_width))
    print(line("TOTAL", str(total.files), _lines_text(total), format_size(total.size_bytes)))


def print_report(stats: dict[StatsKey, Stats], by: str = "both") -> None:
    """Args:
    stats: Result of `collect_stats`. Prints "No files found." instead
        of the tables if it is empty.
    by: `"dir"`, `"type"` or `"both"` - which table(s) to print.
    """
    if not stats:
        print("No files found.")
        return
    if by in ("dir", "both"):
        print_table("By directory", directory_rows(stats))
    if by == "both":
        print()
    if by in ("type", "both"):
        print_table("By type", type_rows(stats))


def _csv_set(raw: str | None) -> set[str] | None:
    """Splits a comma-separated option value into a lower-case set, dots
    stripped (`".py, md"` -> `{"py", "md"}`); `None` stays `None`."""
    if raw is None:
        return None
    return {part.strip().lower().lstrip(".") for part in raw.split(",") if part.strip()}


def main() -> None:
    """CLI entry point: parses the options, scans, and prints the report."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--path",
        type=Path,
        default=REPO_ROOT,
        help="Directory to scan (default: repository root, resolved from this script's own location).",
    )
    parser.add_argument(
        "--by", choices=("dir", "type", "both"), default="both", help="Which table(s) to print (default: both)."
    )
    parser.add_argument("--category", help=f"Count only these categories, comma-separated ({', '.join(CATEGORIES)}).")
    parser.add_argument(
        "--ext",
        help="Count only these extensions, comma-separated (e.g. py,md). `--ext py` gives the old Python-only report.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory name to skip, on top of caches and .venv (repeatable, or comma-separated).",
    )
    parser.add_argument(
        "--tracked",
        action="store_true",
        help="Count only files tracked by git (`git ls-files`) instead of walking the disk.",
    )
    args = parser.parse_args()

    root = args.path.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")
    categories = _csv_set(args.category)
    if categories is not None and not categories <= set(CATEGORIES):
        raise SystemExit(f"Unknown category: {', '.join(sorted(categories - set(CATEGORIES)))}")
    exclude = [name.strip() for raw in args.exclude for name in raw.split(",") if name.strip()]

    stats = collect_stats(
        root,
        tracked_files(root) if args.tracked else None,
        exclude=exclude,
        categories=categories,
        extensions=_csv_set(args.ext),
    )
    print_report(stats, args.by)


if __name__ == "__main__":
    main()
