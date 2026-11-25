# opencode_zen_free

OpenCode Zen: one keyless free-tier shim, an OpenAI Chat Completions lane.

| Provides | Default base URL | Credential |
|:---|:---|:---|
| `opencode_zen_free--chat_completions` | `https://opencode.ai/zen/v1` | none (keyless) |

Maturity: beta (tests plus one live verification). Verified live: 2026-10-16. Tag: `tier:free`. Moved here from `llm-rosetta-shim-contrib/providers/opencode_zen_free`; the shim name did not change.

## Rate limits

- OpenCode Zen: the lane is gated to the OpenCode client's request shape; see the shim's `llm/transforms.py`.

## What the shim fixes

- Model roster: OpenCode's catalog lists the paid models beside the free ones; its `model_list_transform` keeps only the free slice. Request shape: the lane refuses a request that does not declare a tool named exactly `read`; the shim injects a placeholder declaration and removes any call to it from the response.

The lane's client gate was measured live on 2026-10-16 (`llm/transforms.py`, #884).

## Caveats

This is a collection from public sources, not an endorsement. Nothing here guarantees zero data retention, and terms, roster and rate limits belong to the upstream and can change or close without notice. Every endpoint is a third-party service and free tiers may log prompts: never send secrets or personal data through them. The full disclaimer is in [`docs/free-tier.md`](../../docs/free-tier.md).
