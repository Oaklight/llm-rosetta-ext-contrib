# modelscope

ModelScope: Alibaba's model hub, served through an OpenAI-compatible inference gateway. Free API-Inference for registered users.

| Provides |
|---|
| `modelscope--chat_completions` |

Maturity: beta. `since` in the old release metadata: 2026-11-13 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/modelscope`.

## Notes

Measured 2026-11-13: `GET /v1/models` answers 200 with 38 entries in the OpenAI shape and no type field, so the whole catalogue is offered. Access needs a real-name verified Alibaba Cloud account bound to the ModelScope account, and the daily quota is dynamic (2,000 requests/day per user, at most 500 per model).
