"""Print the extension ids a change touches, for CI to test.

A change under ``packages/<id>/`` selects that extension.  A change anywhere
else (the scripts, the shared tests, the workflows) can affect every extension,
so it selects all of them, except documentation-only files.  With no ``--base``
(a push to ``main``) every extension is selected.

    python scripts/changed_packages.py --base origin/main
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Paths whose change cannot change an extension's behaviour.
DOC_ONLY = ("README.md", "CONTRIBUTING.md", "AGENTS.md", "docs/", "skills/", "LICENSE")


def all_ids(root: Path = ROOT) -> list[str]:
    """Every extension folder under ``packages/``."""
    return sorted(
        p.name for p in (root / "packages").iterdir() if (p / "plugin.yaml").is_file()
    )


def select(changed: list[str], everything: list[str]) -> list[str]:
    """Choose the extensions to test for a list of changed paths.

    Args:
        changed: Repo-relative paths with ``/`` separators.
        everything: Every extension id.

    Returns:
        The ids, sorted; all of them when a file outside ``packages/`` that is
        not documentation changed.
    """
    chosen: set[str] = set()
    for path in changed:
        parts = path.split("/")
        if parts[0] == "packages" and len(parts) > 2:
            if parts[1] in everything:
                chosen.add(parts[1])
        elif parts[0] == "packages":
            continue
        elif not path.startswith(DOC_ONLY):
            return sorted(everything)
    return sorted(chosen)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", help="Git ref to compare with (default: select all)")
    args = parser.parse_args(argv)
    everything = all_ids()
    if not args.base:
        print(" ".join(everything))
        return 0
    run = subprocess.run(
        ["git", "diff", "--name-only", f"{args.base}...HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if run.returncode != 0:
        print(run.stderr.strip(), file=sys.stderr)
        return 1
    print(" ".join(select(run.stdout.split(), everything)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
