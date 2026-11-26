"""Build every extension's wheel and the ``index.json`` gateways install from.

``llm-rosetta ext install <id>`` and ``ext update`` read one ``index.json``: for
each extension, the versions published, each with its wheel's URL, ``sha256``,
``Requires-Python`` and what it needs from core.  This script writes the wheels
and that file into ``--out``; the release workflow uploads both as the assets of
one GitHub release, so ``releases/latest/download/index.json`` is always the
newest index.

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
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wheel import BuildError, build_wheel  # noqa: E402

INDEX_VERSION = 1


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


def entry_for(wheel: Path, url: str) -> tuple[str, dict]:
    """Describe one built wheel as ``(extension id, index entry)``."""
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
    return manifest.id, entry


def merge(previous: dict | None, built: dict[str, dict]) -> dict:
    """Combine the earlier index with this run's entries (this run wins)."""
    extensions: dict[str, list[dict]] = {}
    if previous:
        for ext_id, entries in previous.get("extensions", {}).items():
            extensions[ext_id] = list(entries)
    for ext_id, entry in built.items():
        kept = [e for e in extensions.get(ext_id, []) if e["version"] != entry["version"]]
        extensions[ext_id] = [*kept, entry]
    for entries in extensions.values():
        entries.sort(key=lambda e: tuple(int(p) for p in e["version"].split("-")[0].split(".")))
    return {"index_version": INDEX_VERSION, "extensions": dict(sorted(extensions.items()))}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ids", nargs="*", help="Only these extensions (default: all)")
    parser.add_argument("--out", default="dist", help="Directory for the wheels and index.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base-url", help="Where the wheels will be served (no trailing slash)")
    group.add_argument("--relative", action="store_true", help="Use bare wheel file names as URLs")
    parser.add_argument("--previous", help="The last index.json, whose other versions are kept")
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
            ext_id, entry = entry_for(wheel, url)
            built[ext_id] = entry
            print(f"built {ext_id} {entry['version']}  {wheel.name}")
    except BuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    document = merge(previous, built)
    from llm_rosetta.extensions import parse_index

    parse_index(document)  # the installer must be able to read what we publish
    target = out / "index.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} ({sum(len(v) for v in document['extensions'].values())} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
