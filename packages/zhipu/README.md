# zhipu

Zhipu AI's mainland platform (open.bigmodel.cn); `zai` is the international one (api.z.ai). The chat shim keeps the bare name `zhipu`. A model maker's own API with a static key.

| Provides |
|---|
| `zhipu` |
| `zhipu--embedding` |
| `zhipu--rerank` |

Maturity: stable. `since` in the old release metadata: 2026-11-21 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/zhipu`.

## Notes

`since` is the placement decision (#1660 "Placement"). Embeddings measured against embedding-3: a string or list input answers one vector per item and `dimensions` is honoured (2048 -> 512); no parameter default is needed. Rerank measured against model `rerank`: the Cohere request and response shape, both optional parameters (top_n, max_tokens_per_doc) honoured, `document` a plain string when return_documents is set.
