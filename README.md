# llm-rosetta-ext-contrib

Community extensions for [llm-rosetta](https://github.com/Oaklight/llm-rosetta): vendor shims, sign-in exchanges and transports that do not ship with core. Each extension is one self-contained folder under `packages/`.

## Layout

```
README.md  AGENTS.md  CONTRIBUTING.md
skills/                  guidance for coding agents (new-extension, review-extension)
scripts/                 repo-level checks and the index builder
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
llm-rosetta ext install claude        # newest compatible version, by id
llm-rosetta ext install claude --version 0.1.0
llm-rosetta ext update                # every installed extension
llm-rosetta ext install https://…/llm_rosetta_ext_claude-0.1.0-py3-none-any.whl --sha256 <digest>
```

An id is looked up in this repository's latest release (`index.json`, written by the *Release* workflow: each wheel with its sha256, `Requires-Python` and what it needs from core, plus what a listing shows: name, maturity, tags, shims, logo and the commit it was built from. Every field is generated from `plugin.yaml`, the vendor `provider.yaml`, the wheel and git; nothing in the index is written by hand). Point `--index` or `$LLM_ROSETTA_EXTENSION_INDEX` at another index (a URL or a file) to install from a fork or a local mirror. The standard-library installer needs no pip, so it works in the Nuitka binary too; `pip install` of a wheel works as well.

## Extensions

<!-- extensions:start -->
| Id | Name | Provides | Maturity | Tags |
|---|---|---|---|---|
| [`antigravity`](packages/antigravity) | Google (Antigravity) | shims `antigravity--acp` | beta | `tier:subscription`, `auth:cli` |
| [`claude`](packages/claude) | Anthropic Claude (official CLI) | shims `claude--acp`, `claude--messages`; transport `claude_cli` | experimental | `tier:subscription`, `auth:cli` |
| [`groq`](packages/groq) | Groq | shims `groq--chat_completions` | beta | `tier:paid` |
| [`kilo`](packages/kilo) | Kilo | shims `kilo--chat_completions` | beta | `tier:paid` |
| [`kilo_free`](packages/kilo_free) | Kilo (Free) | shims `kilo_free--chat_completions` | beta | `tier:free` |
| [`llm7`](packages/llm7) | LLM7.io | shims `llm7--chat_completions` | beta | `tier:free` |
| [`modelscope`](packages/modelscope) | ModelScope | shims `modelscope--chat_completions` | beta | `tier:paid`, `region:cn` |
| [`moonshot`](packages/moonshot) | Moonshot | shims `moonshot` | stable | `tier:paid`, `region:cn` |
| [`nvidia`](packages/nvidia) | NVIDIA | shims `nvidia--chat_completions` | beta | `tier:paid` |
| [`openai_chatgpt`](packages/openai_chatgpt) | OpenAI (ChatGPT plan) | shims `openai_chatgpt--open_responses` | beta | `tier:subscription`, `auth:oauth` |
| [`opencode`](packages/opencode) | OpenCode | shims `opencode--chat_completions`, `opencode--messages`, `opencode--open_responses` | beta | `tier:subscription`, `tier:paid` |
| [`opencode_zen_free`](packages/opencode_zen_free) | OpenCode Zen | shims `opencode_zen_free--chat_completions` | beta | `tier:free` |
| [`opendesign`](packages/opendesign) | OpenDesign | shims `opendesign--chat_completions`, `opendesign--messages`, `opendesign--open_responses` | beta | `tier:subscription`, `auth:device` |
| [`openrouter`](packages/openrouter) | OpenRouter | shims `openrouter--chat_completions`, `openrouter--messages`, `openrouter--open_responses`, `openrouter--rerank` | beta | `tier:paid` |
| [`ovhcloud`](packages/ovhcloud) | OVHcloud | shims `ovhcloud--chat_completions` | beta | `tier:free` |
| [`qwen`](packages/qwen) | Qwen | shims `qwen` | stable | `tier:paid`, `region:cn` |
| [`siliconflow`](packages/siliconflow) | SiliconFlow | shims `siliconflow--chat_completions`, `siliconflow--embedding`, `siliconflow--rerank` | beta | `tier:paid`, `region:cn` |
| [`volcengine`](packages/volcengine) | Volcengine | shims `volcengine--chat_completions`, `volcengine--embedding`, `volcengine--open_responses` | stable | `tier:paid`, `region:cn` |
| [`xai`](packages/xai) | xAI | shims `xai` | stable | `tier:paid` |
| [`zai`](packages/zai) | Z.ai | shims `zai--chat_completions`, `zai--embedding`, `zai--messages`, `zai--rerank` | stable | `tier:paid` |
| [`zhipu`](packages/zhipu) | Zhipu | shims `zhipu`, `zhipu--embedding`, `zhipu--rerank` | stable | `tier:paid`, `region:cn` |
<!-- extensions:end -->

This table is generated from the `plugin.yaml` files by `scripts/gen_readme_table.py`; CI fails when it is stale.

## Status

All twenty-one extensions load through `llm-rosetta ext`. CI builds each wheel from a clean copy, loads it with core (`scripts/check_wheels.py`), runs `llm-rosetta ext check` and the tests of the changed packages. The *Release* workflow (`.github/workflows/release.yml`, run by hand with a tag) publishes the wheels and `index.json`; it has not been run yet.

Still open: a smoke test against the Nuitka gateway binary.
