"""Check that every extension folder follows the repo layout.

An extension is a directory ``packages/<id>/`` that holds ``plugin.yaml``.
This script only looks at the file system (no YAML parser is needed):

* ``pyproject.toml``, ``README.md``, ``tests/`` exist;
* ``src/llm_rosetta_ext_<id>/`` exists, with ``-`` in the id mapped to ``_``;
* the id is not reserved.

Run from the repo root: ``python scripts/check_layout.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

RESERVED = {"scripts", "skills", "docs", "tests", "packages", "core", "contrib"}


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
        module = "llm_rosetta_ext_" + ext_id.replace("-", "_")
        for rel in ("pyproject.toml", "README.md", "tests", f"src/{module}"):
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
