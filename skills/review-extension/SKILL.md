---
name: review-extension
description: Review a pull request that adds or changes one extension under packages/.
---

Check, in order:

1. The PR touches one `packages/<id>/` folder.
2. No import outside stdlib and `llm_rosetta.contracts.*`; no dependency in `pyproject.toml` beyond `llm-rosetta`.
3. `plugin.yaml` matches what the folder provides (shim names, transports) and its `requires` are not wider than the code uses.
4. Shim names do not collide with core built-ins or another extension.
5. No token or secret in the diff; credentials stay in the vendor store or the credential block.
6. The README says what was verified live and when; the declared `maturity` is justified by it.
Report findings; do not push the fix.
