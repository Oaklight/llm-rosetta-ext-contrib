# llm-rosetta-ext-contrib

Community extensions for [llm-rosetta](https://github.com/Oaklight/llm-rosetta): vendor shims, sign-in exchanges and transports that do not ship with core. Each extension is one self-contained folder under `packages/`.

> Draft layout under review. Nothing here is published, and core does not load this format yet (see *Open items*).

## Layout

```
README.md  AGENTS.md  CONTRIBUTING.md
skills/                  guidance for coding agents (new-extension, review-extension)
scripts/                 repo-level checks and, later, the index builder
.github/workflows/       CI, selected per changed package
packages/
  <id>/                  one extension; owned by its author
    pyproject.toml       own name and version; pip installs it
    plugin.yaml          kind, version, maturity, requires, provides, external
    README.md
    __init__.py          the folder is the package (imported as llm_rosetta_ext.<id>, a PEP 420 namespace package)
    provider.yaml        shim tree (llm/<format>/provider.yaml)
    auth.py quota.py     sidecars (optional)
    transport/           a lane's code (optional)
    tests/
```

An extension is a `packages/<id>/` folder that holds `plugin.yaml`. Extensions never import each other.

## Install

```bash
pip install "git+https://github.com/Oaklight/llm-rosetta-ext-contrib@claude/v0.1.0#subdirectory=packages/claude"
```

Where pip is absent (the Nuitka binary, a slimmed image), the gateway installs the same wheel with a standard-library installer into its data directory. One format, two installers.

## Extensions

| Id | Provides | Maturity |
|---|---|---|
| [`claude`](packages/claude) | shims `claude--acp`, `claude--messages`; transport `claude_cli` | experimental |

This table is generated from `plugin.yaml` files once the index builder exists.

## Open items

1. Core needs the `llm_rosetta.extensions` entry point and the `plugin.yaml` contract (`llm_rosetta.contracts`).
2. `ConnectionConfig.cli_*` fields should become a generic `transport_options`.
3. `claude/auth.py` uses a CLI-login helper that lived at the root of the old contrib package; it must move to core or be vendored.
4. Index builder: wheels per `<id>/vX.Y.Z` tag, sha256, generated README table.
5. Per-package CI and a smoke test against the Nuitka binary.
