"""Check that every extension folder follows the repo layout.

An extension is a directory ``packages/<id>/`` that holds ``plugin.yaml``.
This script only looks at the file system (no YAML parser is needed):

* ``pyproject.toml``, ``README.md``, ``tests/`` exist;
* the id is the folder name: lowercase letters, digits and underscores, the
  same string as the vendor key and the import name ``llm_rosetta_ext.<id>``,
  and ``plugin.yaml`` declares it;
* ``__init__.py`` exists: the folder is the package (a namespace package
  member);
* the id is not reserved.

Run from the repo root: ``python scripts/check_layout.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RESERVED = {"scripts", "skills", "docs", "tests", "packages", "core", "contrib"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def problems(root: Path) -> list[str]:
    found: list[str] = []
    packages = root / "packages"
    for folder in sorted(p for p in packages.iterdir() if p.is_dir()):
        if not (folder / "plugin.yaml").is_file():
            found.append(f"{folder.name}: no plugin.yaml")
            continue
        ext_id = folder.name
        if ext_id in RESERVED:
            found.append(f"{ext_id}: reserved id")
        if not ID_PATTERN.match(ext_id):
            found.append(f"{ext_id}: an id is lowercase letters, digits and underscores")
        declared = re.search(
            r"^id:\s*(\S+)\s*$",
            (folder / "plugin.yaml").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if declared is None or declared.group(1) != ext_id:
            found.append(f"{ext_id}: plugin.yaml must declare id: {ext_id}")
        for rel in ("pyproject.toml", "README.md", "tests", "__init__.py"):
            if not (folder / rel).exists():
                found.append(f"{ext_id}: missing {rel}")
    return found


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    found = problems(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
