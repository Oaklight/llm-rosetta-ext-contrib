# zai

Z.ai: Zhipu AI's international platform (api.z.ai); `zhipu` is the mainland one. One credential serves every lane; the paths differ per model type, so `base_url` stays on each leaf. A model maker's own API with a static key.

| Provides |
|---|
| `zai--chat_completions` |
| `zai--embedding` |
| `zai--messages` |
| `zai--rerank` |

Maturity: stable. `since` in the old release metadata: 2026-11-21 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/zai`.

## Notes

`since` is the placement decision (#1660 "Placement"). Measured 2026-11-13: GET /models lists the catalogue, glm-4.6v-flash answers with `reasoning_content`, and the free `glm-4.7-flash` lane can answer 429 while the service is overloaded. The Messages lane answers 200 with either `x-api-key` or `Authorization: Bearer`, returns `thinking` blocks carrying a `signature`, and accepts `thinking` and `output_config.effort`. Embeddings measured against embedding-3 (OpenAI request shape, float list). Rerank measured against model `rerank` (Cohere request shape, `results[].index/relevance_score`, no `document` field).
