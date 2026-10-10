"""The app's internal version (`0.y.z`), read from the newest entry of
`doc/CHANGELOG.md` - the changelog is where versions are assigned, so there
is no second copy to keep in sync.
"""

import re
from functools import cache
from pathlib import Path

DOC_DIR = Path(__file__).resolve().parents[3] / "doc"
_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)


@cache
def app_version() -> str | None:
    """Returns:
    The first `## x.y.z` heading's version, or `None` if the changelog
    isn't there (e.g. a deployment without `doc/`) or has none.
    """
    # Matched case-insensitively: git tracks the file as `changelog.md`,
    # while Windows checkouts may show `CHANGELOG.md`.
    try:
        path = next(p for p in DOC_DIR.iterdir() if p.name.lower() == "changelog.md")
        match = _HEADING.search(path.read_text(encoding="utf-8"))
    except (OSError, StopIteration):
        return None
    return match.group(1) if match else None
