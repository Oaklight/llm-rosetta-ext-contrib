# Contributing

1. Copy the closest existing folder under `packages/`, rename it to your id, and edit `plugin.yaml`.
2. Keep it self-contained (see `AGENTS.md`). Add tests under `tests/`.
3. `python scripts/check_layout.py`, `llm-rosetta ext check packages/<id>`, then run your package's tests against current llm-rosetta core.
4. Open a pull request that touches only your folder.

Maturity ladder: `experimental` (new) → `beta` (tests and one live verification) → `stable` (candidate for core).
Releases: a maintainer runs the *Release* workflow with a tag. It rebuilds every wheel from a clean copy, merges the previous `index.json` (so older versions stay installable) and uploads the wheels and the new `index.json` as one GitHub release. Bump `version` in `plugin.yaml` and `pyproject.toml` (they must agree) in the pull request that changes an extension.

Users install with `llm-rosetta ext install <id>` and update with `llm-rosetta ext update`; both read the latest release's `index.json` and check each wheel's sha256.
