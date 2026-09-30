"""Bump emliq's version and add a changelog entry in one step.

    python scripts/bump.py patch "Fixed the sync progress speed format"
    python scripts/bump.py minor "Ask AI can answer questions" "Search bar"

patch = fixes and small improvements, minor = new features, major = breaking changes.
Each argument after the level becomes one bullet under the new version.
"""
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "emliq" / "__init__.py"
CHANGELOG = ROOT / "emliq" / "CHANGELOG.md"


def main(level, *changes):
    if level not in ("patch", "minor", "major") or not changes:
        sys.exit(__doc__)
    current = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', INIT.read_text(encoding="utf-8"))
    major, minor, patch = map(int, current.groups())
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    version = f"{major}.{minor}.{patch}"
    INIT.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    entry = f"## {version} — {datetime.date.today().isoformat()}\n" + "".join(f"- {c}\n" for c in changes) + "\n"
    text = CHANGELOG.read_text(encoding="utf-8")
    head, _, rest = text.partition("\n## ")
    CHANGELOG.write_text(f"{head}\n{entry}## {rest}", encoding="utf-8")
    print(f"emliq {version}")


if __name__ == "__main__":
    main(*sys.argv[1:])
