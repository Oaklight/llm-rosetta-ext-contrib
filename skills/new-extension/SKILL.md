---
name: new-extension
description: Add a new extension folder under packages/ (shim, sidecar, transport) following this repo's layout.
---

1. Pick an id (lowercase letters, digits and underscores, not reserved), or run `llm-rosetta ext new <id> --dest packages` (add `--provides transports` or `--provides commands --verb VERB` for those parts). Otherwise copy the closest folder in `packages/`.
2. Fix `pyproject.toml`: `name`, the `package-dir` import name `llm_rosetta_ext.<id>`, the package list, the entry point. Keep `requires-python = ">=3.10"`.
3. Edit `plugin.yaml`: `provides`, `requires`, `external`, `summary`.
4. Write `provider.yaml` files under `llm/<format>/`. Declare every credential field the user must supply.
5. Import only stdlib and `llm_rosetta.contracts.*`.
6. Add tests. Run `python scripts/check_layout.py` and `llm-rosetta ext check packages/<id>`.
7. In the PR body record what you verified live, or say that nothing was.
