# Claude (`claude--messages`) — through the official CLI

Claude as a provider for [llm-rosetta](https://github.com/Oaklight/llm-rosetta),
by running the official **Claude Code CLI** as a model client.

The lane runs `claude -p` in stream-json mode and hands it the conversation as
replay frames. The CLI builds and signs the upstream request itself, so the
gateway never holds a credential: the Claude CLI's own login store is the
account. A per-turn loopback relay forwards the CLI's one upstream request and
gives the gateway the Anthropic Messages stream back, so the target format
stays `messages` and tools stay ordinary IR tools.

> Maturity: **experimental**. The lane is coupled to the CLI's replay and
> request format; re-run the live checks on a CLI version bump. Measured on
> CLI 2.1.299.

## Install

Select the vendor from the contrib source:

```jsonc
{
  "shims": { "sources": ["contrib"], "install": ["claude"] },
  "providers": {
    "claude-cli": {
      "type": "claude--messages",
      "models": ["claude-haiku-4-5", "claude-sonnet-5"]
    }
  }
}
```

The vendor installs both Claude lanes (`claude--acp` and `claude--messages`);
`type` selects the one a provider uses.

## Requirements

- Python >= 3.10
- `llm-rosetta >= 0.14.0.dev40` and a core with the `claude_cli` transport
  (Oaklight/llm-rosetta#1696)
- The official `claude` CLI on the gateway host's `PATH`, or an absolute path
  in `cli_argv`. The lane was measured on 2.1.299.

## Sign in

Sign in once on the gateway host:

```bash
# Claude Pro / Max subscription
claude auth login --claudeai

# or: Anthropic Console, billed per token
claude auth login --console
```

The CLI reads its login store; the gateway stores no token. The shim loads
user settings (`--setting-sources user`) because a host may supply the
credential through an `apiKeyHelper`. Without that flag the CLI starts with no
credential — measured: the upstream answers 401.

## Environment hygiene

Claude Code gives the gateway process's Anthropic settings precedence over the
stored login. The shim removes them from the lane's child process:

- billing and host: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, `ANTHROPIC_CUSTOM_HEADERS`
- model selection: `ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`,
  `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`
- cloud backends: `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
  `CLAUDE_CODE_USE_FOUNDRY`, `CLAUDE_CODE_USE_ANTHROPIC_AWS`,
  `CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD`, `CLAUDE_CODE_USE_MANTLE`,
  `CLAUDE_CODE_USE_GATEWAY`

A provider entry may add names with `cli_env_unset`; it cannot re-admit one the
shim removed.

## Configuration

The shim declares the vendor facts; a provider entry may override them:

```jsonc
{
  "providers": {
    "claude-cli": {
      "type": "claude--messages",
      "cli_argv": ["/opt/claude/bin/claude"],
      "cli_args": ["--setting-sources", "user"],
      "cli_env": { "CLAUDE_CODE_ENTRYPOINT": "my-gateway" },
      "cli_env_unset": ["ANTHROPIC_API_KEY"],
      "cli_upstream": "https://gateway.example"
    }
  }
}
```

- `cli_argv` replaces the command (another install).
- `cli_args` replaces the shim's extra flags. `--setting-sources user` is the
  shim default; keep it when the host authenticates through an `apiKeyHelper`.
- `cli_env` merges over the shim's map; the provider wins.
- `cli_env_unset` adds names to the shim's list.
- `cli_upstream` sends the relay's request to an organization gateway instead
  of Anthropic's API. `https://` only, except a loopback host.

`CLAUDE_CODE_MAX_OUTPUT_TOKENS` in `cli_env` is the hard output ceiling
(measured: 64 reaches the wire body as 64). The lane otherwise leaves
`max_tokens` to the CLI, which asks for 32,000 because its adaptive thinking
shares that budget.

## Capabilities

`[text, vision, reasoning]` are on by default. Images ride through the replay
unchanged (measured against the admin panel's test image); thinking blocks
come back from the CLI's stream events.

`tools` is **off**. The CLI builds the upstream request, and the transport
does not yet inject the host's tool definitions into it: a live request with a
tool degraded to text instead of a `tool_use` block. Tool *history* (`tool_use`
/ `tool_result`, ids and nested content) does replay unchanged, so the gap is
only the outbound definition. Do not give a model on this lane the `tools`
capability until that path is fixed and measured.

## Prompt cache

The CLI appends a `role: "system"` annotation message after every replayed user
message (an environment block naming its per-turn working directory, a date
line). Those blocks sit inside the prefix, so the upstream never reused the
cached one. The relay drops them, requires the host's message count, and moves
the cache breakpoint onto the turn's last block (four at most). A conversation
the CLI reshaped is forwarded unchanged.

Measured on 2.1.299, four turns, ~12K reference corpus: cache-read share
5.4% → 17.8% → 48.4% → 49.9%, against a flat 17.4% before the restore.
`cache_creation_input_tokens` stayed 0 on the organization gateway used for the
measurement.

## Operations

- One `claude` process per request, roughly 250 MB. Cap concurrency per lane;
  queue rather than fail.
- One upstream request per host request. The relay refuses the CLI's recovery
  attempts locally (an upstream 401 admits one retry so the CLI can refresh its
  login).
- The upstream status and `anthropic-ratelimit-*` headers are kept on the turn
  for the quota card and the request log.
- Model ids are passed to `--model` verbatim: a `[1m]` suffix stays the CLI's
  own 1M opt-in, and an unknown id falls back to the CLI's 200K default.

## Terms

Driving the CLI from another client may not be allowed by Anthropic's terms.
This is the same exposure as the ACP lane. Use an account you can afford to
lose.
