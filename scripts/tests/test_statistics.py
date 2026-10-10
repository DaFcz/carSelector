"""Tests for scripts/statistics.py - classification, counting, filters and
the report tables, on a small throwaway tree."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "statistics_script", Path(__file__).resolve().parents[1] / "statistics.py"
)
statistics = importlib.util.module_from_spec(_SPEC)
# Registered before running it: @dataclass looks its module up there.
sys.modules[_SPEC.name] = statistics
_SPEC.loader.exec_module(statistics)


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    files = {
        "backend/app/main.py": "import os\nprint(os)\n",
        "backend/README.md": "# Backend\n\nText\n",
        "backend/.gitignore": "*.pyc\n",
        "backend/__pycache__/main.cpython-312.pyc": b"\0\1\2",
        "doc/spec.pdf": b"%PDF-1.4\0binary",
        "doc/diagram.png": b"\x89PNG\0",
        "doc/notes.weird": "plain text\nsecond\n",
        "doc/blob.weird2": b"abc\0def",
        "storage/catalog.db": b"SQLite format 3\0",
        ".venv/lib/site.py": "x = 1\n",
        "setup.cfg": "[x]\n",
        "LICENSE": "MIT\n",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return tmp_path


def test_classify_known_unknown_and_dotfiles(tree: Path) -> None:
    assert statistics.classify(tree / "backend/app/main.py") == ("source", "py", True)
    assert statistics.classify(tree / "doc/spec.pdf") == ("data", "pdf", False)
    assert statistics.classify(tree / "backend/.gitignore") == ("config", "gitignore", True)
    assert statistics.classify(tree / "doc/notes.weird") == ("other", "weird", True)
    assert statistics.classify(tree / "doc/blob.weird2") == ("other", "weird2", False)
    assert statistics.classify(tree / "LICENSE") == ("other", statistics.NO_EXTENSION, True)


def test_collect_counts_text_lines_and_skips_caches(tree: Path) -> None:
    stats = statistics.collect_stats(tree)

    assert ("backend", "source", "py") in stats
    assert stats[("backend", "source", "py")].lines == 2
    # __pycache__ and .venv are never counted.
    assert not any(ext == "pyc" for _, _, ext in stats)
    assert ".venv" not in {group for group, _, _ in stats}
    # Binary files add files and size, but no lines.
    pdf = stats[("doc", "data", "pdf")]
    assert (pdf.files, pdf.text_files, pdf.lines) == (1, 0, 0)
    assert pdf.size_bytes == len(b"%PDF-1.4\0binary")
    # Files directly in the root are grouped under ".".
    assert (".", "config", "cfg") in stats


def test_filters_and_exclude(tree: Path) -> None:
    only_py = statistics.collect_stats(tree, extensions={"py"})
    assert set(only_py) == {("backend", "source", "py")}

    only_data = statistics.collect_stats(tree, categories={"data"})
    assert {category for _, category, _ in only_data} == {"data"}

    without_storage = statistics.collect_stats(tree, exclude=["storage"])
    assert "storage" not in {group for group, _, _ in without_storage}


def test_directory_rows_have_category_subrows_and_total_counts_once(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stats = statistics.collect_stats(tree)
    rows = statistics.directory_rows(stats)
    labels = [label for label, _ in rows]
    backend = labels.index("backend")
    # Sub-rows follow their directory, in CATEGORIES order.
    assert labels[backend + 1 : backend + 3] == ["  source", "  docs"]

    statistics.print_report(stats, "dir")
    total_line = capsys.readouterr().out.splitlines()[-1]
    all_files = sum(entry.files for entry in stats.values())
    assert total_line.split()[:2] == ["TOTAL", str(all_files)]


def test_binary_only_rows_show_dash_for_lines(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    statistics.print_report(statistics.collect_stats(tree, categories={"data"}), "type")
    out = capsys.readouterr().out
    pdf_line = next(line for line in out.splitlines() if ".pdf" in line)
    assert pdf_line.split()[3] == "-"


def test_tracked_lists_only_git_files(tree: Path) -> None:
    try:
        subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
        subprocess.run(["git", "add", "backend/app/main.py", "doc/spec.pdf"], cwd=tree, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    stats = statistics.collect_stats(tree, statistics.tracked_files(tree))
    assert set(stats) == {("backend", "source", "py"), ("doc", "data", "pdf")}


def test_empty_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    statistics.print_report(statistics.collect_stats(tmp_path))
    assert capsys.readouterr().out.strip() == "No files found."
