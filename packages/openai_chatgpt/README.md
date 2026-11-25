# openai_chatgpt: ChatGPT plan lane

`openai_chatgpt--open_responses` serves the ChatGPT plan allowance
(Go/Plus/Pro), not Platform API billing. It speaks the same Open Responses
wire format as `openai--open_responses`; the credential, the model list and
the accepted request surface differ.

Full user documentation:
<https://llm-rosetta.readthedocs.io/en/latest/guide/providers/openai_chatgpt/>

Maturity: beta (tests plus one live record). Moved here from `llm-rosetta-shim-contrib/providers/openai_chatgpt`.

## Install

```bash
pip install "git+https://github.com/Oaklight/llm-rosetta-ext-contrib@openai_chatgpt/v0.5.1#subdirectory=packages/openai_chatgpt"
```

## Verified live: 2026-11-21

No dated live record is in the tree; the date is the reading of 125 production requests 2026-10-11..2026-11-21 (#1660 usage evidence). `auth.py` is an OAuth exchange (`auth.kind == "oauth"`); `quota.py` carries the in-band `openai_codex` probe the leaf names.

## Credential

- No `api_key_env`: the credential is minted by `auth.py` beside this file.
- Sign in from **Providers → Auth → Start browser sign-in** in the admin
  panel (the gateway returns an authorization URL; the operator pastes the
  callback URL back), or produce a record with
  `llm-rosetta-gateway credential <provider> --out record.json` and install it.
- Starting the browser sign-in again while connected is a re-login: the new
  challenge supersedes a pending one and a completed callback replaces the
  record.
- Access tokens live 3600 s. `connection.token_refresh_interval` is 2880 s so
  the scheduled refresher renews twelve minutes early; a reactive 401 refresh
  covers the rest. Refresh is asynchronous (`asyncio`; blocking HTTP runs on a
  worker thread, commands use an async subprocess).

## Model list

The route answers `{models: [{slug, visibility, …}]}` and the shim keeps the
entries marked `visibility: "list"`. That is the signed-in account's
entitlement, not the Platform API catalogue: expect fewer models than
`openai--open_responses`, and a different set per plan or app grant. Fetch the
list again after a plan change.

## Request surface

`store: false` is forced; `previous_response_id` and the fields listed in
`llm/transforms.py` are stripped. A `system`/`developer` item anywhere in
`input` is refused by the route (`400 System messages are not allowed`), so the
shim also runs the IR hoist transform: leading items become `instructions`,
late ones user turns. Streaming is required — a non-streaming Responses client
is refused with `400` naming `stream=true`. Only the `web_search` hosted tool is
declared. The plan allowance is in-band only: the probe classifies refusals and
is never polled.
