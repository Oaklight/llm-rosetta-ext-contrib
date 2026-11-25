# kilo

Kilo's paid gateway. The keyless free pool is a different shim, `kilo_free--chat_completions`, so this lane always authenticates: a provider on it without a key is refused rather than silently sent upstream unauthenticated.

| Provides |
|---|
| `kilo--chat_completions` |

Maturity: beta. `since` in the old release metadata: 2026-11-21 (Notes say what it dates).

Moved here from `llm-rosetta-shim-contrib/providers/kilo`.

## Notes

No dated live record in the tree; production requests 2026-10-11..2026-11-21 (#1660 usage evidence).
