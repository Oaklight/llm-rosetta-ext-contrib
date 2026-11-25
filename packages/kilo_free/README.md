# kilo_free

Kilo (Free): one keyless free-tier shim, an OpenAI Chat Completions lane.

| Provides | Default base URL | Credential |
|:---|:---|:---|
| `kilo_free--chat_completions` | `https://api.kilo.ai/api/gateway` | none (keyless) |

Maturity: beta (tests plus one live verification). Verified live: 2026-11-13. Tag: `tier:free`. Moved here from `llm-rosetta-shim-contrib/providers/kilo_free`; the shim name did not change.

## Rate limits

- Kilo: 200 requests per hour per IP on the free pool.

## What the shim fixes

- Model roster: Kilo's catalog lists the paid models beside the free ones; its `model_list_transform` keeps only the free slice. The free lane carries no reasoning rename: its reasoning field has not been probed, and an unverified rename is worse than none.

Kilo ships on both sides: the paid gateway is the built-in `kilo--chat_completions` (always sends `KILO_API_KEY`, offers the whole catalogue), and the keyless pool is `kilo_free--chat_completions` here. Keeping the two contracts apart is what lets the paid leaf demand a credential.

## Caveats

This is a collection from public sources, not an endorsement. Nothing here guarantees zero data retention, and terms, roster and rate limits belong to the upstream and can change or close without notice. Every endpoint is a third-party service and free tiers may log prompts: never send secrets or personal data through them. The full disclaimer is in [`docs/free-tier.md`](../../docs/free-tier.md).
