# openrouter

OpenRouter lanes on one credential. `openrouter--messages` answers on `https://openrouter.ai/api` while the other lanes carry `/api/v1`, so `base_url` stays on each leaf.

| Provides |
|---|
| `openrouter--chat_completions` |
| `openrouter--messages` |
| `openrouter--open_responses` |
| `openrouter--rerank` |

Maturity: beta. `since` in the old release metadata: 2026-11-19 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/openrouter`.

## Notes

Measured live 2026-11-19 (llm/open_responses). Confirmed live 2026-10-12 (#899): OpenRouter rejects `store: true` with HTTP 400, returns a `gen-...` id with no `resp_` prefix, and emits none of the OpenAI lifecycle/echo fields; no profile traits are declared, by design. Rerank measured against rerank-v3.5 (served by Cohere through OpenRouter): the Cohere request and response shape, top_n and max_tokens_per_doc accepted; return_documents is ignored (documents always come back), so the shim declares no parameter defaults.
