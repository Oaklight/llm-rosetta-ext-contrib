# groq

Groq: LPU inference on an OpenAI-compatible endpoint.

| Provides |
|---|
| `groq--chat_completions` |

Maturity: beta. `since` in the old release metadata: 2026-11-13 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/groq`.

## Notes

Measured 2026-11-13: `GET /openai/v1/models` answers 401 without a key, so the endpoint exists and authenticates as documented; chat itself has not been probed (llm/transforms.py). The free plan gives the chat models 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD; exact limits are per organisation and are read from the account limits page.
