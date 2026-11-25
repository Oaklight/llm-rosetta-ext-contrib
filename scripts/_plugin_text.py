"""Read the few plugin.yaml fields the repo scripts need, without a YAML parser.

The scripts are standard-library only.  They read the fields the schema fixes
as simple scalars and flat lists (``id``, ``name``, ``version``, ``maturity``,
``tags``, ``provides.shims``, ``provides.transports``); anything richer is the
loader's job (``llm-rosetta ext check`` validates the whole manifest).
"""

from __future__ import annotations

import re
from pathlib import Path


def _unquote(text: str) -> str:
    return text.strip().strip("\"'")


def scalar(text: str, key: str) -> str | None:
    match = re.search(rf"^{key}:\s*(.+?)\s*$", text, re.MULTILINE)
    return _unquote(match.group(1)) if match else None


def flat_list(text: str, key: str) -> list[str]:
    """A list written ``key: [a, b]`` or as ``key:`` followed by ``- a`` lines."""
    flow = re.search(rf"^\s*{key}:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if flow:
        return [_unquote(s) for s in flow.group(1).split(",") if s.strip()]
    block = re.search(rf"^\s*{key}:\s*\n((?:\s+-\s+\S+\n?)+)", text, re.MULTILINE)
    if block:
        return [_unquote(s) for s in re.findall(r"-\s+(\S+)", block.group(1))]
    return []


def read(folder: Path) -> dict[str, object]:
    text = (folder / "plugin.yaml").read_text(encoding="utf-8")
    return {
        "id": scalar(text, "id"),
        "name": scalar(text, "name"),
        "version": scalar(text, "version"),
        "maturity": scalar(text, "maturity"),
        "tags": flat_list(text, "tags"),
        "shims": flat_list(text, "shims"),
        "transports": flat_list(text, "transports"),
    }
