#!/usr/bin/env python3
"""Prints a quick file/line/size summary of this repository's own Python
source, broken down by top-level directory (backend, scraper, scripts, ...).

Only counts .py files that are actually part of the project - not the
virtual environment, VCS metadata, or tool caches (see _EXCLUDED_DIRS
below), since those would dwarf the real numbers with third-party library
code and aren't "this project's source" in any useful sense.

Usage (run from anywhere - the scan root is resolved from this script's own
location, not the current working directory):

    python scripts/statistics.py
    scripts\\statistics.bat            (Windows double-click wrapper, see that file)
    python scripts/statistics.py --path backend    (scan a subtree instead)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directory names that hold generated/vendored content rather than this
# project's own source - matched against every path component, so a nested
# occurrence (e.g. backend/app/__pycache__) is excluded too, not just one
# at the repo root.
_EXCLUDED_DIRS = {".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


@dataclass
class DirStats:
    """File/line/size counts accumulated for one top-level directory."""

    files: int = 0
    lines: int = 0
    size_bytes: int = 0


def format_size(size_bytes: int) -> str:
    """Args:
        size_bytes: A byte count, e.g. `DirStats.size_bytes`.

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


def is_excluded(path: Path) -> bool:
    """Args:
        path: A candidate .py file's absolute path.

    Returns:
        True if any component of `path` names a non-source directory (see
        _EXCLUDED_DIRS) - i.e. the file should not be counted.
    """
    return any(part in _EXCLUDED_DIRS for part in path.parts)


def top_level_group(path: Path, root: Path) -> str:
    """Args:
        path: A candidate .py file's absolute path, somewhere under `root`.
        root: The scan root `path` was found under.

    Returns:
        `path`'s top-level directory name relative to `root` (e.g.
        `"backend"`, `"scraper"`, `"scripts"`), or `"."` for a file that
        sits directly in `root` with no subdirectory in between.
    """
    relative_parts = path.relative_to(root).parts
    return relative_parts[0] if len(relative_parts) > 1 else "."


def collect_stats(root: Path) -> dict[str, DirStats]:
    """Args:
        root: Directory to scan for .py files (recursively).

    Returns:
        Per-top-level-directory `DirStats` (see `top_level_group`) for
        every `*.py` file under `root` that isn't excluded (see
        `is_excluded`). Files that aren't valid UTF-8 are still counted,
        with undecodable bytes ignored (`errors="ignore"`).
    """
    stats: dict[str, DirStats] = {}
    for path in root.rglob("*.py"):
        if is_excluded(path):
            continue
        entry = stats.setdefault(top_level_group(path, root), DirStats())
        entry.files += 1
        entry.lines += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        entry.size_bytes += path.stat().st_size
    return stats


def print_report(stats: dict[str, DirStats]) -> None:
    """Args:
        stats: Result of `collect_stats` - printed as one file/line/size
            line per top-level directory (sorted by name), followed by a
            TOTAL line. Prints "No .py files found." instead if `stats`
            is empty.
    """
    if not stats:
        print("No .py files found.")
        return

    name_width = max(len(name) for name in stats)
    total_files = sum(entry.files for entry in stats.values())
    total_lines = sum(entry.lines for entry in stats.values())
    total_size = sum(entry.size_bytes for entry in stats.values())
    size_width = max(len(format_size(entry.size_bytes)) for entry in stats.values())
    size_width = max(size_width, len(format_size(total_size)))

    for name in sorted(stats):
        entry = stats[name]
        print(
            f"{name:<{name_width}}  {entry.files:>5} files  {entry.lines:>7} lines  "
            f"{format_size(entry.size_bytes):>{size_width}}"
        )
    print(f"{'-' * name_width}  {'-' * 5}--------  {'-' * 7}-------  {'-' * size_width}")
    print(
        f"{'TOTAL':<{name_width}}  {total_files:>5} files  {total_lines:>7} lines  "
        f"{format_size(total_size):>{size_width}}"
    )


def main() -> None:
    """CLI entry point: parses `--path`, scans it, and prints the report."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=REPO_ROOT,
        help="Directory to scan (default: repository root, resolved from this script's own location).",
    )
    args = parser.parse_args()

    root = args.path.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    print_report(collect_stats(root))


if __name__ == "__main__":
    main()
