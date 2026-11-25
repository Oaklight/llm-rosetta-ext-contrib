# Contributing

1. Copy the closest existing folder under `packages/`, rename it to your id, and edit `plugin.yaml`.
2. Keep it self-contained (see `AGENTS.md`). Add tests under `tests/`.
3. `python scripts/check_layout.py`, then run your package's tests against current llm-rosetta core.
4. Open a pull request that touches only your folder.

Maturity ladder: `experimental` (new) → `beta` (tests and one live verification) → `stable` (candidate for core).
Releases are per extension: tag `<id>/vX.Y.Z`.
