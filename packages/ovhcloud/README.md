# ovhcloud

OVHcloud: one keyless free-tier shim, an OpenAI Chat Completions lane.

| Provides | Default base URL | Credential |
|:---|:---|:---|
| `ovhcloud--chat_completions` | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` | none (keyless) |

Maturity: beta (tests plus one live verification). Verified live: 2026-11-13. Tag: `tier:free`. Moved here from `llm-rosetta-shim-contrib/providers/ovhcloud`; the shim name did not change.

## Rate limits

- OVHcloud: 2 requests per minute per IP per model, anonymous. A Public Cloud project key raises it to 400 RPM per project per model and bills per token.

## What the shim fixes

- Reasoning field: OVHcloud puts reasoning text on `message.reasoning` / `delta.reasoning`, while the Chat Completions converter reads `reasoning_content`. The shim ships a rename, a no-op when no reasoning is present. Model roster: OVHcloud's listing carries no type field and is offered whole.

## Caveats

This is a collection from public sources, not an endorsement. Nothing here guarantees zero data retention, and terms, roster and rate limits belong to the upstream and can change or close without notice. Every endpoint is a third-party service and free tiers may log prompts: never send secrets or personal data through them. The full disclaimer is in [`docs/free-tier.md`](../../docs/free-tier.md).
