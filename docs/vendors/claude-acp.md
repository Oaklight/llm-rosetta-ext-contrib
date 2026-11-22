# Claude (`claude`) — over ACP

Claude as a provider for [llm-rosetta](https://github.com/Oaklight/llm-rosetta),
through the **Claude Agent SDK ACP adapter**
([`@agentclientprotocol/claude-agent-acp`](https://github.com/agentclientprotocol/claude-agent-acp)).

The lane starts the adapter as a local ACP agent. The adapter runs Claude Code
(the native CLI shipped with the Claude Agent SDK) and exposes it over ACP.
No gateway credential is involved: the Claude CLI's own login store
(`~/.claude`) is the account.

> Maturity: **experimental**. The adapter is versioned independently, and its
> permission surface is larger than the gateway can see. A live tool round trip
> through a Claude Pro subscription is recorded (adapter 0.109.1, Claude Code
> 2.1.299): the request's `echo` tool returned as a tool call and the client's
> result resumed the same ACP turn.

## Install

Select the vendor from the contrib source:

```jsonc
{
  "shims": { "sources": ["contrib"], "install": ["claude"] }
}
```

Installing the Python distribution also works: `pip install
llm-rosetta-shim-contrib` registers the vendor through its `claude` entry
point.

## Requirements

- Python >= 3.10
- `llm-rosetta >= 0.14.0.dev35` (the manifest records
  `requires: {surface: 1, ir: 1}`)
- Node.js **22 or newer** and `npx` on the gateway host
- A core that reads `connection.acp_env` (Oaklight/llm-rosetta#1675). An older
  core ignores the key, so Claude Code's tool search stays on and the request's
  bridged tools are not called directly. The core surface level does not rise
  for an added field, so check the core build rather than `requires.surface`.

The shim pins `@agentclientprotocol/claude-agent-acp@0.109.1`. The package
bundles the Claude Agent SDK and its native Claude CLI, so a global `claude`
install is not required. A separately installed CLI can be selected with
`CLAUDE_CODE_EXECUTABLE`, and a separate Claude profile with
`CLAUDE_CONFIG_DIR`. Set the latter through a provider's `acp_env` (below).

## Sign in

Sign in once on the gateway host with the Claude Code CLI:

```bash
# Claude Pro / Max subscription
claude auth login --claudeai

# or: Anthropic Console, billed per token
claude auth login --console
```

The adapter shares the CLI's credential store, so this login covers the lane.

### Use a clean profile

A full profile (`~/.claude`) can carry the host's entire skill catalog. A live
run with a large profile reached `Prompt is too long · ~201543 tokens` against
the 200,000-token limit. For a gateway lane, use a clean profile and point the
provider at it:

```bash
mkdir -p /srv/llm-rosetta/claude-pro
chmod 700 /srv/llm-rosetta/claude-pro
# Copy only the credential file from the profile you signed in with.
install -m 600 ~/.claude/.credentials.json \
  /srv/llm-rosetta/claude-pro/.credentials.json

# With CLAUDE_CONFIG_DIR pointing at that directory, this should report
# authMethod "claude.ai" and the subscription type.
CLAUDE_CONFIG_DIR=/srv/llm-rosetta/claude-pro claude auth status --json
```

```jsonc
{
  "providers": {
    "claude": {
      "type": "claude--acp",
      "acp_env": { "CLAUDE_CONFIG_DIR": "/srv/llm-rosetta/claude-pro" }
    }
  }
}
```

`acp_env` is layered over the gateway's own environment, so `PATH` and the
login store remain available; a value in the provider entry wins over one the
shim declares. The shim itself sets `ENABLE_TOOL_SEARCH=false` (see
[Tool calls](#tool-calls)).

A Pro/Max plan is subject to Anthropic's usage windows. An enterprise profile
used during verification answered `You've hit your 5-hour limit`; that is the
plan's limit, not a gateway error. The successful verification used a Pro
profile at 43,335 of 200,000 tokens.

**Do not set `ANTHROPIC_API_KEY`** in the gateway's environment. When that
variable is present, Claude Code uses API billing instead of the subscription.
The same applies to provider/gateway environment variables that reroute the
Claude CLI.

Anthropic's terms may not allow third-party ACP clients. Use an account you can
afford to lose.

## Configure a provider

```jsonc
{
  "shims": { "sources": ["contrib"], "install": ["claude"] },
  "providers": {
    "claude": {
      "type": "claude--acp"
    }
  },
  "models": {
    "claude-opus-4-6": { "provider": "claude" }
  }
}
```

The shim supplies the adapter command. The `base_url` in the manifest is a
placeholder: an ACP lane starts a process and never dials that host.

## Tool calls

Two tool paths exist and they are not the same.

**Client tools** — tools declared by the API request — are served to the
adapter as a loopback HTTP MCP endpoint named `llm_rosetta_tools` in
`session/new`. Claude Code calls the tool through MCP; the gateway returns the
call to the API client and answers the pending MCP request when the next API
request carries the tool result. This is the normal tool-calling contract.

The lane's default capabilities are `[text, vision, reasoning, tools]`. The
live round trip above recorded the whole path, so a model receives client tools
without opting in. A model that must not receive them can declare the other
capabilities explicitly:

```jsonc
{
  "models": {
    "claude-opus-4-6": {
      "provider": "claude",
      "capabilities": ["text", "vision", "reasoning"]
    }
  }
}
```

Claude Code's tool search would otherwise defer the MCP tools behind its own
`ToolSearch` built-in, which the gateway treats as a built-in tool and refuses.
The shim therefore sets `ENABLE_TOOL_SEARCH=false` in `connection.acp_env`.
Do not override it unless you also change how the built-in guard treats that
call.

Client tools need a conversation id. The client's result is matched to the
suspended turn by that id, so a request that declares tools without one is
refused with `400` rather than losing the call. Declare a session id in a
header (`x-claude-code-session-id`, `x-opencode-session`, an
`x-<vendor>-session-id` whose value looks like an id) or in the body
(`metadata.user_id.session_id` or `prompt_cache_key`).

The declared tool set is a property of the session, not of one turn. The
adapter fixes its MCP server list when a session opens, so a request whose
tools differ from that session's — a tool added or removed, a tool disabled,
or a refreshed schema — closes the session and replays the conversation into
a fresh one that lists the new set. A tool-result request that also changes
the tool set does the same: the gateway abandons the suspended call and
replays the history rather than continuing with the old bridge. Expect such a
request to cost a full history replay.

**Claude Code's own tools** (file read and write, shell, web) are not a
gateway tool path. The gateway refuses every built-in tool permission request
it receives and stops a turn at a built-in tool frame. However, Claude Code may
auto-approve some read-only tools without sending a permission request, so this
lane cannot guarantee that it never reads a file on the gateway host. Run the
gateway on a host where that is acceptable.

## Limitations

- The adapter's output includes plans, subagent transcripts, terminals and
  edit reviews. The lane carries text, thinking, images, usage and tool calls;
  the rest is dropped.
- ACP turns have no sampling parameters, so `temperature`, `top_p` and similar
  settings are reported as dropped conversion warnings.
- The adapter version is pinned in the shim. Update the shim version to move it.
- Subscription windows are Anthropic's and are not visible to the gateway. An
  exhausted plan reads as the adapter's own error, not a gateway error.
- A full Claude profile can load the host's skill catalog and exceed the context
  window. Point `CLAUDE_CONFIG_DIR` at a clean profile for each lane.
- Claude Code's own tools are refused, but some read-only tools may be
  auto-approved before a permission request reaches the gateway.
