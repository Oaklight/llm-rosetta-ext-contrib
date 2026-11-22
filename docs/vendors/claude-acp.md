# Claude (`claude`) — over ACP

Claude as a provider for [llm-rosetta](https://github.com/Oaklight/llm-rosetta),
through the **Claude Agent SDK ACP adapter**
([`@agentclientprotocol/claude-agent-acp`](https://github.com/agentclientprotocol/claude-agent-acp)).

The lane starts the adapter as a local ACP agent. The adapter runs Claude Code
(the native CLI shipped with the Claude Agent SDK) and exposes it over ACP.
No gateway credential is involved: the Claude CLI's own login store
(`~/.claude`) is the account.

> Maturity: **experimental**. The adapter is versioned independently, its
> permission surface is larger than the gateway can see, and no live run
> through this lane is recorded yet.

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

The shim pins `@agentclientprotocol/claude-agent-acp@0.109.1`. The package
bundles the Claude Agent SDK and its native Claude CLI, so a global `claude`
install is not required. A separately installed CLI can be selected with
`CLAUDE_CODE_EXECUTABLE`.

## Sign in

Sign in once on the gateway host with the Claude Code CLI:

```bash
# Claude Pro / Max subscription
claude auth login --claudeai

# or: Anthropic Console, billed per token
claude auth login --console
```

The adapter shares the CLI's credential store, so this login covers the lane.

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

The lane's default capabilities are `[text, vision, reasoning]`. The tool path
is implemented and tested against a fake ACP agent, but a live round trip
through this adapter is not recorded, so `tools` is not declared by default.
Opt in per model when you want it:

```jsonc
{
  "models": {
    "claude-opus-4-6": {
      "provider": "claude",
      "capabilities": ["text", "vision", "reasoning", "tools"]
    }
  }
}
```

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
