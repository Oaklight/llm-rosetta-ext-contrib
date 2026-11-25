# llm7

LLM7.io: one keyless free-tier shim, an OpenAI Chat Completions lane.

| Provides | Default base URL | Credential |
|:---|:---|:---|
| `llm7--chat_completions` | `https://api.llm7.io/v1` | none (keyless) |

Maturity: beta (tests plus one live verification). Verified live: 2026-11-13. Tag: `tier:free`. Moved here from `llm-rosetta-shim-contrib/providers/llm7`; the shim name did not change.

## Rate limits

- LLM7: anonymous access reaches the `turbo` models. A free token from `token.llm7.io` raises the rate ceiling to 1 RPS / 60 RPM / 250 requests per hour / 100,000 tokens per 24 h, and reaches the same models.

## What the shim fixes

- Reasoning field: LLM7 puts reasoning text on `message.reasoning` / `delta.reasoning`, while the Chat Completions converter reads `reasoning_content`. The shim ships a rename, a no-op when no reasoning is present. Model roster: LLM7's catalog is typed and tiered, so its transform keeps `model_type: chat` in the `turbo` tier.

## Caveats

This is a collection from public sources, not an endorsement. Nothing here guarantees zero data retention, and terms, roster and rate limits belong to the upstream and can change or close without notice. Every endpoint is a third-party service and free tiers may log prompts: never send secrets or personal data through them. The full disclaimer is in [`docs/free-tier.md`](../../docs/free-tier.md).
