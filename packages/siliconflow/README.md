# siliconflow

SiliconFlow: free and paid models on one credential. The typed catalogue lives on a second host, so `models_path` is an absolute URL on each leaf.

| Provides |
|---|
| `siliconflow--chat_completions` |
| `siliconflow--embedding` |
| `siliconflow--rerank` |

Maturity: beta. `since` in the old release metadata: 2026-11-13 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/siliconflow`.

## Notes

Measured 2026-11-13: chat, embeddings (BAAI/bge-m3, float list in the OpenAI shape) and rerank (BAAI/bge-reranker-v2-m3, Cohere request shape, `results[].index/relevance_score`) answer 200. The plain /v1/models carries no type field, so the picker cannot tell a chat model from an image one; the playground endpoint on a second host tags every entry with `type`/`subType` and a `status` of `normal` or `disable` (measured: 201 entries, 91 active, 61 of them `subType: chat`). The shim owns that URL and its transform keeps the active chat slice.
