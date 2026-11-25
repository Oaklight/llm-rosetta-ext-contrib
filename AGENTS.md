# AGENTS.md

Rules for coding agents working in this repository.

## Shape

- An extension is `packages/<id>/` with `plugin.yaml`, `pyproject.toml`, `README.md`, `__init__.py` (the folder is the package, imported as `llm_rosetta_ext.<id>`; the parent `llm_rosetta_ext` is a PEP 420 namespace and must never get an `__init__.py`) and `tests/`.
- One pull request changes one extension. Repo-level files (`scripts/`, `skills/`, CI) go in their own pull request.
- Run `python scripts/check_layout.py` before you push.

## Imports

- An extension imports only the standard library and `llm_rosetta.contracts.*`. Never `llm_rosetta_gateway`, never a private core name, never another extension.
- No third-party dependencies. The gateway may run where pip is absent, so an extension must work from a plain unzip.
- The id is the vendor key and the import name: lowercase letters, digits and underscores (`kilo_free`, not `kilo-free`). A shim name is `<id>`, `<id>--<name>` or `<id>_<lane>--<name>` (`alcf_sophia--chat_completions` under `alcf`). It must not equal a core built-in shim name; ids are unique across extension repositories.

## Manifest (draft schema)

`plugin.yaml` keys: `id`, `name`, `version`, `maturity` (`experimental|beta|stable`), `tags`, `requires.surface`, `requires.ir`, `provides.shims`, `provides.transports`, `external` (name, check, minimum, install_hint), `platforms`, `summary.en`, `summary.zh`.

## Rules that cost us before

- Credentials stay in the vendor's own store or in the gateway's credential block. Never write a token to a file in the extension.
- Record live verification in the extension's README (date, what was called). `beta` needs tests plus one live verification.
- Do not hard-wrap prose in issues and pull requests.
