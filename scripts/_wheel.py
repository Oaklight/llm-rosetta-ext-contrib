"""Build one extension's wheel from a clean copy of its folder.

The folder is the package, so a build writes ``build/`` and ``*.egg-info``
inside it, and a second build would pick those up as package content.  Building
from a copy that leaves them out means a developer's earlier builds cannot
change the result.  ``pip wheel --no-deps`` needs no network.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class BuildError(RuntimeError):
    """The wheel could not be built."""


def build_wheel(folder: Path, out: Path) -> Path:
    """Build ``folder`` into a wheel inside ``out`` and return its path.

    Args:
        folder: The extension folder, ``packages/<id>``.
        out: A directory the wheel (and the clean copy) are written under; the
            wheel itself lands directly in it.

    Returns:
        The path of the one wheel built.

    Raises:
        BuildError: The build failed or produced no single wheel.
    """
    out.mkdir(parents=True, exist_ok=True)
    source = out / f".src-{folder.name}" / folder.name
    if source.parent.exists():
        shutil.rmtree(source.parent)
    shutil.copytree(
        folder,
        source,
        ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__", "*.pyc"),
    )
    before = set(out.glob("*.whl"))
    run = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(out), str(source)],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(source.parent, ignore_errors=True)
    made = sorted(set(out.glob("*.whl")) - before)
    if run.returncode != 0 or len(made) != 1:
        raise BuildError(
            f"{folder.name}: wheel build failed: {run.stderr.strip()[-400:]}"
        )
    return made[0]
