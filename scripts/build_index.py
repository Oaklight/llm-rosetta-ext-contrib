"""Build every extension's wheel and the ``index.json`` gateways install from.

``llm-rosetta ext install <id>`` and ``ext update`` read one ``index.json``: for
each extension, the versions published, each with its wheel's URL, ``sha256``,
``Requires-Python``, what it needs from core, and what a listing shows (name,
maturity, tags, shims, logo, the commit it was built from).  This script writes
the wheels and that file into ``--out``; the release workflow uploads both as the
assets of one GitHub release, so ``releases/latest/download/index.json`` is
always the newest index.

Nothing in the index is written by hand.  Every field is read from a source file:
``plugin.yaml`` (inside the built wheel) gives the id, version, name, maturity,
tags, shims and requirements; the vendor ``provider.yaml`` gives the logo; the
wheel gives ``sha256`` and ``Requires-Python``; git gives ``commit`` (the last
commit that touched the extension's folder); the repository name gives
``source``; the clock gives ``generated_at`` (``SOURCE_DATE_EPOCH`` overrides it,
for a reproducible build).

An index lists every version ever published, so a release carries the earlier
ones forward: ``--previous`` is the last release's ``index.json``, and an entry
whose version this run did not rebuild is kept as it was (its URL already points
at the release that holds that wheel).

Needs an llm-rosetta core that has ``llm_rosetta.extensions`` on ``PYTHONPATH``
or installed.  Run from the repo root::

    python scripts/build_index.py --out dist \\
        --base-url https://github.com/<owner>/<repo>/releases/download/<tag> \\
        [--previous previous-index.json] [id ...]

With ``--relative`` the URLs are the wheel file names, which resolve against the
index: a directory of wheels and an index is a self-contained mirror.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wheel import BuildError, build_wheel  # noqa: E402

INDEX_VERSION = 1

#: A vendor-level ``logo:`` line (no indentation: lane files nest theirs).
_LOGO_RE = re.compile(r"^logo:\s*(.+?)\s*$", re.MULTILINE)
_SOURCE_PREFIXES = ("llm-rosetta-ext-", "llm-rosetta-shim-")


def requires_python(wheel: Path) -> str | None:
    """Read ``Requires-Python`` from a wheel's ``METADATA``."""
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            if len(parts) == 2 and parts[0].endswith(".dist-info") and parts[1] == "METADATA":
                for line in archive.read(name).decode("utf-8", "replace").splitlines():
                    if not line.strip():
                        return None
                    key, _, value = line.partition(":")
                    if key.strip().lower() == "requires-python":
                        return value.strip() or None
    return None


def vendor_logo(wheel: Path, ext_id: str) -> str | None:
    """Read the vendor-level ``logo:`` from the wheel's ``provider.yaml``."""
    with zipfile.ZipFile(wheel) as archive:
        try:
            text = archive.read(f"llm_rosetta_ext/{ext_id}/provider.yaml").decode("utf-8")
        except KeyError:
            return None
    found = _LOGO_RE.search(text)
    if found is None:
        return None
    value = re.split(r"\s#", found.group(1), maxsplit=1)[0].strip().strip("'\"")
    return value or None


def last_commit(folder: Path) -> str | None:
    """The last commit that touched ``folder``, or ``None`` outside a git checkout."""
    run = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(folder)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    sha = run.stdout.strip()
    return sha if run.returncode == 0 and sha else None


def default_source() -> str:
    """The repository's short name: ``llm-rosetta-ext-contrib`` is ``contrib``."""
    name = os.environ.get("GITHUB_REPOSITORY", "").rsplit("/", 1)[-1] or ROOT.name
    for prefix in _SOURCE_PREFIXES:
        name = name.removeprefix(prefix)
    name = name.lower()
    return name if re.match(r"^[a-z][a-z0-9_-]*$", name) else ""


def timestamp() -> str:
    """Now as RFC 3339 UTC; ``SOURCE_DATE_EPOCH`` fixes it for a reproducible build."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = (
        datetime.fromtimestamp(int(epoch), timezone.utc)
        if epoch
        else datetime.now(timezone.utc)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_for(wheel: Path, url: str, folder: Path | None = None) -> tuple[str, dict]:
    """Describe one built wheel as ``(extension id, index entry)``.

    Args:
        wheel: The built wheel.
        url: Where the wheel will be served.
        folder: The extension's source folder, for ``commit``.
    """
    from llm_rosetta.extensions import inspect_wheel

    manifest = inspect_wheel(wheel)
    entry: dict = {
        "version": manifest.version,
        "url": url,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "surface": manifest.requires.surface,
        "ir": manifest.requires.ir,
    }
    spec = requires_python(wheel)
    if spec:
        entry["requires_python"] = spec
    if manifest.requires.extensions:
        entry["requires_extensions"] = list(manifest.requires.extensions)
    entry["name"] = manifest.name
    entry["maturity"] = manifest.maturity
    entry["tags"] = list(manifest.tags)
    entry["shims"] = list(manifest.shims)
    logo = vendor_logo(wheel, manifest.id)
    if logo:
        entry["logo"] = logo
    commit = last_commit(folder) if folder is not None else None
    if commit:
        entry["commit"] = commit
    return manifest.id, entry


def merge(
    previous: dict | None,
    built: dict[str, dict],
    *,
    source: str = "",
    generated_at: str = "",
) -> dict:
    """Combine the earlier index with this run's entries (this run wins).

    The header is this run's: ``source`` and ``generated_at`` when given.
    """
    extensions: dict[str, list[dict]] = {}
    if previous:
        for ext_id, entries in previous.get("extensions", {}).items():
            extensions[ext_id] = list(entries)
    for ext_id, entry in built.items():
        kept = [e for e in extensions.get(ext_id, []) if e["version"] != entry["version"]]
        extensions[ext_id] = [*kept, entry]
    for entries in extensions.values():
        entries.sort(key=lambda e: tuple(int(p) for p in e["version"].split("-")[0].split(".")))
    document: dict = {"index_version": INDEX_VERSION}
    if source:
        document["source"] = source
    if generated_at:
        document["generated_at"] = generated_at
    document["extensions"] = dict(sorted(extensions.items()))
    return document


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ids", nargs="*", help="Only these extensions (default: all)")
    parser.add_argument("--out", default="dist", help="Directory for the wheels and index.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base-url", help="Where the wheels will be served (no trailing slash)")
    group.add_argument("--relative", action="store_true", help="Use bare wheel file names as URLs")
    parser.add_argument("--previous", help="The last index.json, whose other versions are kept")
    parser.add_argument(
        "--source", help="The repository's short name (default: from the repository name)"
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    folders = [
        p
        for p in sorted((ROOT / "packages").iterdir())
        if (p / "plugin.yaml").is_file() and (not args.ids or p.name in args.ids)
    ]
    if not folders:
        print("no extension selected", file=sys.stderr)
        return 2
    previous = None
    if args.previous and Path(args.previous).is_file():
        previous = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    built: dict[str, dict] = {}
    try:
        for folder in folders:
            wheel = build_wheel(folder, out)
            url = wheel.name if args.relative else f"{args.base_url.rstrip('/')}/{wheel.name}"
            ext_id, entry = entry_for(wheel, url, folder)
            built[ext_id] = entry
            print(f"built {ext_id} {entry['version']}  {wheel.name}")
    except BuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    document = merge(
        previous,
        built,
        source=args.source or default_source(),
        generated_at=timestamp(),
    )
    from llm_rosetta.extensions import parse_index

    parse_index(document)  # the installer must be able to read what we publish
    target = out / "index.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} ({sum(len(v) for v in document['extensions'].values())} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
