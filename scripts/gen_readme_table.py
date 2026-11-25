"""Write the extension table of README.md from the plugin.yaml files.

The table sits between ``<!-- extensions:start -->`` and
``<!-- extensions:end -->``.  ``python scripts/gen_readme_table.py`` rewrites
it; ``--check`` exits 1 when the committed table is stale, which is what CI runs,
so the table can never drift from the manifests.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _plugin_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- extensions:start -->", "<!-- extensions:end -->"


def table() -> str:
    rows = ["| Id | Name | Provides | Maturity | Tags |", "|---|---|---|---|---|"]
    for folder in sorted((ROOT / "packages").iterdir()):
        if not (folder / "plugin.yaml").is_file():
            continue
        info = _plugin_text.read(folder)
        provides = []
        if info["shims"]:
            provides.append("shims " + ", ".join(f"`{s}`" for s in info["shims"]))
        if info["transports"]:
            provides.append(
                "transport " + ", ".join(f"`{s}`" for s in info["transports"])
            )
        tags = ", ".join(f"`{t}`" for t in info["tags"])
        rows.append(
            f"| [`{info['id']}`](packages/{folder.name}) | {info['name']} | "
            f"{'; '.join(provides)} | {info['maturity']} | {tags} |"
        )
    return "\n".join(rows)


def rewrite(text: str) -> str:
    start, end = text.index(START), text.index(END)
    return text[: start + len(START)] + "\n" + table() + "\n" + text[end:]


def main(argv: list[str]) -> int:
    readme = ROOT / "README.md"
    current = readme.read_text(encoding="utf-8")
    updated = rewrite(current)
    if "--check" in argv:
        if updated != current:
            print("README.md extension table is stale: run scripts/gen_readme_table.py")
            return 1
        return 0
    readme.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
