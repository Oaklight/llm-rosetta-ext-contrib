# llm-rosetta-shim-opendesign

Open Design Cloud as a provider for
[llm-rosetta](https://github.com/Oaklight/llm-rosetta), delivered as a **plugin
package** rather than as a built-in shim.

Open Design Cloud serves its models on a single HTTPS gateway. The three chat
formats this package exposes all talk to that gateway; only the authentication
header and the wire body differ.

## Install

Declare the preset in the gateway config:

```jsonc
{
  "shims": { "presets": ["opendesign"] }
}
```

The preset resolves to this repository and its bundled provider directory
through llm-rosetta's catalogue. The equivalent explicit entry is:

```jsonc
{
  "shims": {
    "remotes": [
      {
        "url": "https://github.com/Oaklight/llm-rosetta-shim-opendesign",
        "path": "src/llm_rosetta_shim_opendesign/providers"
      }
    ]
  }
}
```

Installing the distribution directly also works; llm-rosetta discovers the
`llm_rosetta.shim_providers` entry point on its own:

```bash
pip install llm-rosetta-shim-opendesign
```

## Requirements

- Python >= 3.10
- `llm-rosetta >= 0.14.0.dev31` (the vendor manifest carries the mark as a
  manifest-level `logo:`; dev30 and earlier refuse that file, so the entry point
  fails to load instead of registering the shims — 0.14.0 and later are above
  this floor too)

## Configure a provider

```jsonc
{
  "shims": { "presets": ["opendesign"] },
  "providers": {
    "opendesign": {
      "type": "opendesign--chat_completions"
    }
  },
  "models": {
    "deepseek-v4.1-flash": { "provider": "opendesign" }
  }
}
```

The vendor manifest supplies the base URL and the model-list URL, and a
provider entry may override them. There is deliberately no `api_key` in the
entry: the shim ships a credential exchange (`auth.py`), and the gateway
refuses a static key beside an exchange it does not consume. The provider
therefore starts out needing a sign-in.

## Sign in

Open Design splits one account across two planes:

- the **model plane** serves model traffic with the runtime key (`sk-amr-…`);
- the **control plane** serves account and Coding Plan reads with the control
  key (`vela_ctrl_…`).

The web UI never shows the control key. The only way to obtain it is the
device-authorization flow, which this package implements in
`src/llm_rosetta_shim_opendesign/providers/opendesign/auth.py`:

1. The gateway starts a device authorization and shows an activation URL and
   a short user code.
2. A human opens the URL, signs in, and approves the device.
3. The next poll returns both keys at once. The record is written with mode
   `0600` under the gateway's `<data_dir>/shim-auth/<provider>` (or, when the
   gateway has no data directory, under `~/.config/llm-rosetta/opendesign/`).
4. `credential()` serves the runtime key. The control key is stored beside it
   for the allowance reader.

From a machine with a browser, run the sign-in locally and hand the record to
the gateway:

```bash
llm-rosetta-gateway credential opendesign --out /tmp/opendesign-record.json
# then: admin panel → Providers → opendesign → Credential, or
#       PUT /admin/api/config/providers/opendesign/credential
```

The admin panel's own sign-in button runs the same flow server-side: it starts
the device authorization, and each "complete" call polls once until approved.

The keys do not expire and the vendor issues no refresh token, so there is no
rotation. `revoke()` removes the record and returns `False`: the vendor
documents no revocation endpoint, so the keys stay live until Open Design
rotates them.

## The shims

| Shim | Format | Endpoint | Credential header |
|:---|:---|:---|:---|
| `opendesign--chat_completions` | `chat_completions` | `/v1/chat/completions` | `Authorization: Bearer sk-amr-…` |
| `opendesign--open_responses` | `open_responses` | `/v1/responses` | `Authorization: Bearer sk-amr-…` |
| `opendesign--messages` | `messages` | `/v1/messages` | `x-api-key: sk-amr-…` + `anthropic-version: 2023-06-01` |

Base URL: `https://amr-link.open-design.ai/v1`.
Model listing: `https://amr-link.open-design.ai/v1/models`.

The runtime API key (`sk-amr-…`) is the credential for every model request.
Open Design serves every model on all three APIs, so pick the format the
client speaks; the shim signs the request the way that endpoint expects.

## Quota

The Coding Plan allowance is read on the **control plane**, with the control
key (`vela_ctrl_…`) the same sign-in stores beside the runtime key.
`providers/opendesign/quota.py` implements the probe, and it declares
`credential_role = "control"`: the gateway asks `auth.py` for that credential
and marks the reading **advisory** — shown on the panel, able to weight the
lane's share, and never evidence for a demotion, an exclusion or a recovery
time, because none of those is about the control key.

The read takes three requests — `workspaces/current`, the workspace's
`billing/preflight`, then `billing/summary` for the tier — so the probe uses
the contract's multi-step `fetch` instead of the default single GET:

- two windows, `durationSeconds` 18000 (5 hours) and 604800 (7 days);
- `used_percent` clamped to 100 — the 7-day window can report more used than
  its limit while `remainingCredits` is already `"0"`;
- `resets_at` in ISO 8601, and the membership tier as the plan name.

Without a control key the gateway reports the provider's quota as unsupported
and makes no billing request: there is no fallback to the runtime key, which
the control plane answers with 401.

The manifest declares the block once, because the allowance is the account's
rather than a lane's:

```yaml
quota:
  probe: opendesign
  url: https://amr-api.open-design.ai
```

**Release ordering, and what an older core sees.** `credential_role` and
`fetch` are core contract additions. On a core that carries them the card
works; on an older one the probe imports (the two names are imported
defensively) and reports the lane as having no keyed endpoint, so the panel
says the allowance is unsupported and the lane keeps serving — it never sends
the runtime key to a plane that would answer 401. The `quota:` block is
likewise declared on each leaf rather than in the manifest, because a core
older than the manifest's `quota:` key refuses that file outright. Both move
up — the block to the manifest, the dependency floor to that dev release —
when the core ships, and the two are one edit.

## Archive and mirror

Every release publishes one archive of the bundled shims, so a gateway can load
them from a host other than GitHub. `main` never carries it: `dist/` is build
output and is in `.gitignore`.

- `v<version>/opendesign.tar.gz` and `v<version>/opendesign.tar.gz.sha256` live
  on the orphan `dist` branch.
- The same bytes are attached to the GitHub Release, with the digest in its
  notes.

The archive's root is `providers/`, the layout the package ships under
`src/llm_rosetta_shim_opendesign/providers`, so a gateway source declares
`path: "providers"`:

```jsonc
{
  "shims": {
    "remotes": [
      {
        "url": "https://cdn.jsdelivr.net/gh/Oaklight/llm-rosetta-shim-opendesign@dist/v<version>/opendesign.tar.gz",
        "path": "providers",
        "archive": "tar.gz",
        "sha256": "<digest from v<version>/opendesign.tar.gz.sha256>"
      }
    ]
  }
}
```

## Live behavior

The endpoint, header split, model-list path, device flow, and the three
control-plane reads were exercised against a live Open Design account on
2026-11-14:

- `GET /v1/models` with the runtime key answers 200 (14 models);
- the runtime key on the control plane answers 401, and the control key on the
  model plane answers 401 (`invalid_api_key`) — the two are not
  interchangeable;
- `workspaces/current`, the workspace's `billing/preflight`, and
  `billing/summary` answer 200 and match the shapes the probe normalises,
  including a 7-day window whose `usedCredits` (150218) exceeded its
  `limitCredits` (150000) with `remainingCredits` already `"0"`.

One measured gotcha is encoded in both modules: the control plane sits behind
a CDN that rejects urllib's default user agent outright (Cloudflare error
1010), so every request sends `User-Agent: open-design-cli/<cliVersion>`.

No credential is stored in this repository; the test suite fakes the HTTP
layer and covers registration, the bundled manifests, the device-flow state
machine, and the quota normalisation.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e . pytest pyyaml
pytest tests -q
python scripts/build_shim_archive.py
```
