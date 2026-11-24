# Claude (`claude`) — over ACP

Claude as a provider for [llm-rosetta](https://github.com/Oaklight/llm-rosetta),
through the **Claude Agent SDK ACP adapter**
([`@agentclientprotocol/claude-agent-acp`](https://github.com/agentclientprotocol/claude-agent-acp)).

The lane starts the adapter as a local ACP agent. The adapter runs Claude Code
(the native CLI shipped with the Claude Agent SDK) and exposes it over ACP.
No gateway credential is involved: the Claude CLI's own login store is the
account. The shim points that store at the lane's persistent directory under
the gateway data directory (`CLAUDE_CONFIG_DIR={acp_home}/claude`), so a
mounted data volume carries the login into the next container image.

> Maturity: **experimental**. The adapter is versioned independently. The
> pinned adapter is given `disableBuiltInTools: true`, so the lane offers only
> the gateway's bridged tools; another adapter version must be checked for that
> key. A live tool round trip through a Claude Pro subscription is recorded
> (adapter 0.109.1, Claude Code 2.1.299): the request's `echo` tool returned as
> a tool call and the client's result resumed the same ACP turn.

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
- `llm-rosetta >= 0.14.0.dev40` (the first core with the vendor-managed
  exchange, `connection.acp_session_meta` and `connection.acp_env_unset`; the
  manifest records `requires: {surface: 1, ir: 1}`)
- Node.js **22 or newer** and `npx` on the gateway host
- A core that reads `connection.acp_env` (Oaklight/llm-rosetta#1675). An older
  core ignores the key, so Claude Code's tool search stays on and the request's
  bridged tools are not called directly. The core surface level does not rise
  for an added field, so check the core build rather than `requires.surface`.
- A core with the persistent ACP home (Oaklight/llm-rosetta#1683): it expands
  `{acp_home}` and publishes `LLM_ROSETTA_ACP_HOME`. An older core passes the
  placeholder literally, so the CLI would try to use a directory with braces in
  its name. The manifest's `>= 0.14.0.dev40` floor includes both changes and
  the session `_meta` that removes Claude Code's built-in tools.

The shim pins `@agentclientprotocol/claude-agent-acp@0.109.1`. The package
bundles the Claude Agent SDK and its native Claude CLI, so a global `claude`
install is not required. A separately installed CLI can be selected with
`CLAUDE_CODE_EXECUTABLE`. The shim sets `CLAUDE_CONFIG_DIR` to the lane's
persistent home; a provider's `acp_env` may override it with another saved
profile.

## Sign in

Sign in once on the gateway host with the Claude Code CLI:

```bash
# Claude Pro / Max subscription
claude auth login --claudeai

# or: Anthropic Console, billed per token
claude auth login --console
```

The adapter shares the CLI's credential store, so this login covers the lane.

### Sign in from the admin panel

The admin panel drives the same CLI, so the operator does not need a shell on
the gateway host. Open the provider's credential page and choose **Sign in**;
the panel shows the URL the CLI printed and accepts the code or callback URL
the signed-in page gives back.

The panel uses the CLI named by `acp_env.CLAUDE_CODE_EXECUTABLE`, or `claude`
on the gateway's `PATH`, and the profile named by
`acp_env.CLAUDE_CONFIG_DIR`. The gateway stores no token: the account shown
comes from `claude auth status --json`.

### The lane's own profile

The shim does not use the host's `~/.claude`. It points
`CLAUDE_CONFIG_DIR` at `{acp_home}/claude`, where `acp_home` is the lane's
persistent home: `<data_dir>/acp/<provider-name>` by default. The sign-in
writes the Claude credential there once, and every later ACP session of that
provider reuses it.

Because the home lives under `server.data_dir`, mounting that directory on a
volume keeps the login across a gateway restart and across an image upgrade.
The next container reads the same credential store and needs no new sign-in.
The published image declares `/config` as a volume and keeps its data in
`/config/data`, so a volume on `/config` is enough.

`acp.home` selects a different home. An absolute path is used as written, `~`
is expanded, and a relative path is taken under the data directory. Two
provider entries with different homes hold two independent logins and two
independent profiles:

```jsonc
{
  "providers": {
    "claude": {
      "type": "claude--acp",
      "acp": { "home": "/srv/llm-rosetta/claude-pro" }
    }
  }
}
```

A new home starts empty, so the lane avoids the host's skill catalog. A live
run with a full `~/.claude` profile reached `Prompt is too long · ~201543
tokens` against the 200,000-token limit. Sign in again in the empty home
rather than copying a full profile.

The shim also sets `npm_config_cache={acp_home}/npm`. `npx` would otherwise
cache the adapter under the process's `HOME`, which a container replaces with
each image; on the volume the next image reuses the installed package instead
of downloading it again.

### Switch the adapter version

The agent command names an **install**; `acp.home` names the **profile**. The
shim pins `@agentclientprotocol/claude-agent-acp@0.109.1` in
`connection.acp_argv`. Point the provider entry's `acp.argv` at another version
and the login store does not move:

```jsonc
{
  "providers": {
    "claude": {
      "type": "claude--acp",
      "acp": {
        "argv": ["npx", "-y", "@agentclientprotocol/claude-agent-acp@0.110.0"],
        "home": "saved/claude-pro"
      }
    }
  }
}
```

The older top-level `acp_argv` still works as an alias. Because the npm cache
and `CLAUDE_CONFIG_DIR` both live under `acp.home`, a version switch needs no
new sign-in; keep the home and change only the command. `acp.argv` needs a
core that reads it; this package's `0.14.0.dev40` floor includes that change.

`acp_env` is layered over the environment the gateway starts the agent with.
`CLAUDE_CODE_EXECUTABLE` names a specific CLI binary and `CLAUDE_CONFIG_DIR`
another profile directory; a value in the provider entry wins over one the
shim declares. `LLM_ROSETTA_ACP_HOME` is the exception: it is gateway-owned,
and `acp.home` is the way to move the profile. The shim itself sets
`ENABLE_TOOL_SEARCH=false` (see [Tool calls](#tool-calls)).

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
a fresh one that lists the new set. Order alone is not a difference: the
session's tool digest is canonical, so the same definitions in another order
keep the session. A tool-result request that also changes
the tool set does the same: the gateway abandons the suspended call and
replays the history rather than continuing with the old bridge. Expect such a
request to cost a full history replay.

**Claude Code's own tools** (file read and write, shell, web) are not a
gateway tool path. The shim passes `disableBuiltInTools: true` on
`session/new` (and repeats it on `session/load` and `session/resume`, which the
adapter folds into its session fingerprint), so the agent's built-in list is
empty and the only tools it can call are the request's, served over the
loopback MCP bridge. The gateway also refuses every built-in permission request
and stops a turn that starts one, as a second line. Only an adapter version
that ignores `disableBuiltInTools` would expose the built-ins; check that key
before changing the pin.

## Limitations

- The adapter's output includes plans, subagent transcripts, terminals and
  edit reviews. The lane carries text, thinking, images, usage and tool calls;
  the rest is dropped.
- ACP turns have no sampling parameters, so `temperature`, `top_p` and similar
  settings are reported as dropped conversion warnings.
- The adapter version is pinned in the shim. Override `acp.argv` on a provider
  entry to run another version without moving `acp.home` (see
  [Switch the adapter version](#switch-the-adapter-version)).
- Subscription windows are Anthropic's and are not visible to the gateway. An
  exhausted plan reads as the adapter's own error, not a gateway error.
- A full Claude profile can load the host's skill catalog and exceed the context
  window. The lane's own home starts empty; keep it that way.
- Built-in tools are removed by the pinned adapter's `disableBuiltInTools`
  session key; an adapter that ignores it could expose them, so change the pin
  deliberately and re-run the live check.
