# volcengine

Volcengine ARK, domestic (China mainland) endpoint; international is `ark.ap-southeast.bytepluses.com/api/v3`. A model maker's own API with a static key.

| Provides |
|---|
| `volcengine--chat_completions` |
| `volcengine--embedding` |
| `volcengine--open_responses` |

Maturity: stable. `since` in the old release metadata: 2026-11-21 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/volcengine`.

## Notes

`since` is the placement decision (#1660 "Placement"). ARK returns `resp_`-prefixed response ids, so the prefix is stripped on the way in and re-added on the way out; it is the one provider outside OpenAI where `store_default: true` is correct (omitting `store` yields `store: true`, and `store: false` echoes false); it emits none of the OpenAI lifecycle fields. All verified live 2026-10-12 (#899). Embeddings measured against doubao-embedding-text-240715: a list input answers one vector per item, `encoding_format=base64` is honoured, `dimensions` is accepted but ignored (the vector stays 2560), so the shim declares no parameter defaults.
