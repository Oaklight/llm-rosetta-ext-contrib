"""Build every extension's wheel and load it the way a gateway would.

For each ``packages/<id>/`` this script

1. builds a pure-Python wheel (``pip wheel --no-deps``, so no network),
2. checks that the wheel carries every file of the folder except the packaging
   and test files (a missing ``provider.yaml`` or sidecar would otherwise only
   show up on a user's machine),
3. unzips it with the standard library into a temp directory and, in a fresh
   interpreter, runs core's ``load_extensions()`` against that directory,
4. checks the extension's status is ``loaded`` and that the shims it registered
   are exactly the ones its ``plugin.yaml`` provides.

Needs an llm-rosetta core that has ``llm_rosetta.extensions`` on ``PYTHONPATH``
or installed.  Run from the repo root: ``python scripts/check_wheels.py [id ...]``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOT_SHIPPED = {"pyproject.toml", "README.md"}
NOT_SHIPPED_DIRS = {"tests", "build", "__pycache__"}

PROBE = """
import json, sys
from llm_rosetta.extensions import list_extensions, load_extensions
load_extensions()
print(json.dumps([
    {"id": s.id, "state": s.state, "reason": s.reason, "shims": list(s.shims)}
    for s in list_extensions()
]))
"""


def expected_files(folder: Path) -> set[str]:
    files: set[str] = set()
    for path in folder.rglob("*"):
        rel = path.relative_to(folder)
        if not path.is_file() or rel.parts[0] in NOT_SHIPPED_DIRS:
            continue
        if len(rel.parts) == 1 and rel.name in NOT_SHIPPED:
            continue
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        if any(part.endswith(".egg-info") for part in rel.parts):
            continue
        files.add(f"llm_rosetta_ext/{folder.name}/{rel.as_posix()}")
    return files


def declared_shims(folder: Path) -> list[str]:
    text = (folder / "plugin.yaml").read_text(encoding="utf-8")
    match = re.search(r"^\s*shims:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if match:
        return [s.strip().strip("\"'") for s in match.group(1).split(",") if s.strip()]
    block = re.search(r"^\s*shims:\s*\n((?:\s+-\s+\S+\n?)+)", text, re.MULTILINE)
    if block:
        return [s.strip("\"'") for s in re.findall(r"-\s+(\S+)", block.group(1))]
    return []


def check(folder: Path, work: Path) -> list[str]:
    problems: list[str] = []
    out = work / folder.name
    out.mkdir()
    # The folder is the package, so a build writes ``build/`` and ``*.egg-info``
    # inside it, and a second build would pick those up as package content.
    # Build from a clean copy so a developer's earlier builds cannot matter.
    source = out / "src" / folder.name
    shutil.copytree(
        folder,
        source,
        ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__", "*.pyc"),
    )
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(out), str(source)],
        capture_output=True,
        text=True,
    )
    wheels = list(out.glob("*.whl"))
    if build.returncode != 0 or len(wheels) != 1:
        return [f"{folder.name}: wheel build failed: {build.stderr.strip()[-400:]}"]
    with zipfile.ZipFile(wheels[0]) as archive:
        names = {n for n in archive.namelist() if n.startswith("llm_rosetta_ext/")}
        target = out / "site"
        archive.extractall(target)
    expected = expected_files(folder)
    for missing in sorted(expected - names):
        problems.append(f"{folder.name}: wheel lacks {missing}")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(target), *filter(None, [env.get("PYTHONPATH")])]
    )
    probe = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, env=env
    )
    if probe.returncode != 0:
        return [*problems, f"{folder.name}: probe failed: {probe.stderr.strip()[-400:]}"]
    statuses = json.loads(probe.stdout.strip().splitlines()[-1])
    status = next((s for s in statuses if s["id"] == folder.name), None)
    if status is None:
        problems.append(f"{folder.name}: core did not discover it")
    elif status["state"] != "loaded":
        problems.append(f"{folder.name}: {status['state']}: {status['reason']}")
    else:
        want = sorted(declared_shims(folder))
        if sorted(status["shims"]) != want:
            problems.append(
                f"{folder.name}: registered {sorted(status['shims'])}, plugin.yaml says {want}"
            )
    return problems


def main(argv: list[str]) -> int:
    folders = [
        p
        for p in sorted((ROOT / "packages").iterdir())
        if (p / "plugin.yaml").is_file() and (not argv or p.name in argv)
    ]
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for folder in folders:
            problems = check(folder, Path(tmp))
            print(("FAIL " if problems else "ok   ") + folder.name)
            for line in problems:
                print("     " + line)
            failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
