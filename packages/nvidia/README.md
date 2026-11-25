# nvidia

NVIDIA NIM: hosted open-weight models from build.nvidia.com, signed with a developer-program key. One credential for every endpoint.

| Provides |
|---|
| `nvidia--chat_completions` |

Maturity: beta. `since` in the old release metadata: 2026-11-13 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/nvidia`.

## Notes

Measured 2026-11-13: `GET /v1/models` answers 200 and lists 83 entries in the OpenAI shape with no type field, so the whole catalogue is offered. Hosted endpoints are for prototyping and testing; production use needs an NVIDIA AI Enterprise licence (NIM FAQ).
