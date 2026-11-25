# opencode: OpenCode Go and Zen

OpenCode as a provider for [llm-rosetta](https://github.com/Oaklight/llm-rosetta), over three chat formats.

| Provides | Format |
|---|---|
| `opencode--chat_completions` | `chat_completions` |
| `opencode--open_responses` | `open_responses` |
| `opencode--messages` | `messages` |

Go (monthly subscription) and Zen (account balance) share one key; the default is the Go subscription lane. For the Zen balance lane set Base URL to `https://opencode.ai/zen/v1`. The Go allowance probe is `quota.py`. The keyless free pool ships as its own package (`opencode_zen_free`).

Maturity: beta (tests plus one live verification). Moved here from `llm-rosetta-shim-contrib/providers/opencode`, which took it from core (Oaklight/llm-rosetta#1660 S7); the tree is unchanged, so every shim keeps its name.

## Install

```bash
pip install "git+https://github.com/Oaklight/llm-rosetta-ext-contrib@opencode/v0.5.1#subdirectory=packages/opencode"
```

## Verified live: 2026-10-13

Probed live 2026-10-13 (`llm/messages`); about 99k production requests 2026-10-11..2026-11-21 (#1660 usage evidence).
