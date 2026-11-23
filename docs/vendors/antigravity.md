# Google Antigravity (`antigravity`) — over ACP

Antigravity as a provider for
[llm-rosetta](https://github.com/Oaklight/llm-rosetta), through the vendor's
own `agy` CLI over ACP.

The lane does not call Google's Code Assist API. It starts `agy acp` and speaks
the Agent Client Protocol to it, so the Google sign-in, the access token and
the project stay with `agy`. This is deliberately the least indirect way to use
the plan: Google suspends accounts it sees calling Code Assist outside
Antigravity's own client, and driving the vendor's CLI keeps the request inside
the client Google expects. That risk is not removed.

## Install

```jsonc
{
  "shims": { "sources": ["contrib"], "install": ["antigravity"] }
}
```

Installing `llm-rosetta-shim-contrib` also registers the vendor through its
`antigravity` entry point.

## Requirements

- Python >= 3.10
- `llm-rosetta >= 0.14.0.dev38` (the first core whose exchanges may be
  vendor-managed)
- `agy` on the gateway host (the profile measures come from `agy` 1.5.13;
  the live tool round trip from 1.5.14)

## Sign in

Run `agy` once in a terminal on the gateway host and complete the Google
sign-in, or use the admin panel's **Sign in** button. Both drive the same
`agy acp --login`; the panel shows the URL and writes the pasted code back.

The shim declares the lane keyless: the gateway never holds the Google token.
The panel reads the account address and token expiry from the keyring
(`service=gemini`, `username=antigravity`) and never returns the token itself.

## Configure a provider

```jsonc
{
  "shims": { "sources": ["contrib"], "install": ["antigravity"] },
  "providers": {
    "antigravity": {
      "type": "antigravity--acp"
    }
  },
  "models": {
    "gemini-3.1-pro": { "provider": "antigravity" }
  }
}
```

## Tool policy

`agy` approves its own tools by default, which would hand the gateway host to
every client of the gateway. The transport therefore starts `agy` in a
gateway-owned profile (`--gemini-dir <data_dir>/acp/<provider>`) and re-asserts
it before every turn:

- a custom agent with no tools;
- a `PreToolUse` hook that permits only the gateway's loopback MCP server;
- `toolPermission: strict` with `permissions.allow: ["mcp(*)"]`;
- `--process-per-session`.

Every built-in tool permission request is refused, and a turn in which `agy`
starts a built-in tool is stopped with HTTP 502.

**Client tools** — tools declared by the API request — are different. They are
served to `agy` as a loopback HTTP MCP endpoint named `llm_rosetta_tools` in
`session/new`. `agy` 1.5.14 calls one by its direct MCP name
(`mcp_llm_rosetta_tools_<tool>`); 1.5.13 used the `call_mcp_tool` meta-tool.
The gateway hands the call to the API client and answers the pending MCP
request when the next API request carries the result.

The bridge is tested in core against a fake ACP agent and live-verified
against `agy` 1.5.14: the request's `echo` tool reached the agent, the agent's
call suspended the turn, the client's result resumed it, and the agent replied
with that result. Version 1.5.14 names an MCP tool directly
(`mcp_llm_rosetta_tools_echo`); 1.5.13 routed it through `call_mcp_tool`. The
gateway's hook allows both shapes for its own server and nothing else, so
`tools` is on by default. A model that must not receive client tools can
declare the other capabilities explicitly:

```jsonc
{
  "models": {
    "gemini-3.1-pro": {
      "provider": "antigravity",
      "capabilities": ["text", "vision", "reasoning"]
    }
  }
}
```

## Limitations

- A custom `acp_argv` gets none of the profile and re-enables host tools, at
  the operator's own risk.
- ACP turns carry no sampling parameters; those settings are reported as
  dropped conversion warnings.
- Google may suspend an account used outside Antigravity's own client. Use an
  account you can afford to lose.
