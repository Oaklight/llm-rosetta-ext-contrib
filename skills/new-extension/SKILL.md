---
name: new-extension
description: Add a new extension folder under packages/ (shim, sidecar, transport) following this repo's layout.
---

1. Pick an id (lowercase, `-` allowed, not reserved). Copy the closest folder in `packages/`.
2. Rename `src/llm_rosetta_ext_<old>` to `src/llm_rosetta_ext_<id>` and fix `pyproject.toml` (`name`, entry point).
3. Edit `plugin.yaml`: `provides`, `requires`, `external`, `summary`.
4. Write `provider.yaml` files under `llm/<format>/`. Declare every credential field the user must supply.
5. Import only stdlib and `llm_rosetta.contracts.*`.
6. Add tests. Run `python scripts/check_layout.py`.
7. In the PR body record what you verified live, or say that nothing was.
