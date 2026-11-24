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
- `llm-rosetta >= 0.14.0.dev39` (the first core whose exchanges may be
  vendor-managed, whose ACP lanes get a persistent home, and which reads
  `acp.argv` plus the three-state `acp.harden`; see Oaklight/llm-rosetta#1681,
  #1683 and #1684)
- `agy` on the gateway host (the profile measures come from `agy` 1.5.13;
  the live tool round trip from 1.5.14)

## Sign in

Run `agy` once in a terminal on the gateway host and complete the Google
sign-in, or use the admin panel's **Sign in** button. Both drive the same
`agy acp --login`, and the gateway passes `--gemini-dir <acp_home>`, so the
login lands in the lane's persistent profile. The panel shows the URL and
writes the pasted code back.

`acp_home` is the lane's persistent home: `<data_dir>/acp/<provider-name>` by
default. On a desktop host `agy` stores the token in the system keyring
(`service=gemini`, `username=antigravity`); the panel reads the account
address and token expiry from there and never returns the token itself.

On a headless host without a keyring, `agy` falls back to a token file under
`--gemini-dir`. The file stays in the persistent home, so mounting
`server.data_dir` on a volume reuses the login after a restart or an image
upgrade. The published image declares `/config` as a volume and keeps its data
in `/config/data`, so a volume on `/config` is enough. In this mode the panel
cannot read the token store; it records a non-secret marker in
`<acp_home>/.llm-rosetta-login.json` after the CLI reports success and shows
the lane as connected. The gateway never holds the Google token. On such a
host `Connected` means "the CLI last reported a successful sign-in", not that
the token is still valid.

**Sign out** removes the headless marker and, on a desktop host, the `agy`
keyring entry. It does not revoke the Google grant upstream. Removing the
marker returns the lane to its setup state, so the next render offers the
sign-in again.

### Switch or share a profile

`acp.home` selects another home; an absolute path is used as written, `~` is
expanded, and a relative path is taken under the data directory. The same
setting drives the agent's `--gemini-dir` and the panel's sign-in, so the two
cannot disagree:

```jsonc
{
  "providers": {
    "antigravity": {
      "type": "antigravity--acp",
      "acp": { "home": "/srv/llm-rosetta/gemini-work" }
    }
  }
}
```

A desktop keyring is one entry for the whole installation, so a keyring-backed
host shares one Google account across provider entries. A headless host keeps
one login per home.

### Switch the installed version

The agent command names an **install**; `acp.home` names the **profile**. To
run another `agy` build, point `acp.argv` at it and leave the home in place:

```jsonc
{
  "providers": {
    "antigravity": {
      "type": "antigravity--acp",
      "acp": {
        "home": "saved/antigravity-work",
        "argv": ["/opt/agy-1.7/bin/agy", "acp"]
      }
    }
  }
}
```

The older top-level `acp_argv` remains an alias. Hardening follows the
executable name by default: a command whose executable is `agy` keeps
`--gemini-dir`, the no-tools agent, the deny-all hook and the session gate, so
a switch to another `agy` build neither re-enables host tools nor costs the
sign-in. A renamed download (`agy-1.7`) or a wrapper is not recognised by
name; set `acp.harden: true` to force the profile on it (a wrapper must pass
`agy`'s flags through), or `acp.harden: false` to run it as written. An
unhardened `agy` command must name `--gemini-dir`, so the agent and the
sign-in still share one profile.

A command that hides the whole call in a shell string — `["bash", "-lc", "…
agy acp"]` — has no literal `acp` token for the sign-in to keep, so the panel
refuses to drive it rather than guessing a command. Use `["<agy>", "acp"]`, or
run the CLI's own sign-in in that profile.

Inside the published container, put the install under the mounted data
directory — for example `/config/data/acp/antigravity/install/agy` — and point
`argv` at it. The image replaces its own filesystem on upgrade; `/config` is
the volume, so the next image starts the same binary and finds the same login.

The admin sign-in runs the same install and, when the command already names
`--gemini-dir`, writes that directory. Leave `acp.home` unset then, or set it
to the same path: two different directories are refused rather than split
between the agent and its sign-in. `acp.argv` needs a core that reads it;
this package's `0.14.0.dev39` floor includes that change.

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
gateway-owned profile (`--gemini-dir <acp_home>`) and re-asserts
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

## Allowance

`agy acp` turns carry only token counts, so the Quota card is filled by the
vendor CLI itself. The shim declares `quota.local`, and the gateway runs the
same CLI with the lane's profile:

```
agy -p "/usage" --output-format json
```

`{acp_argv0}` expands to the lane's declared `acp.argv[0]`, so the read follows
the install the lane uses. Print mode does not accept `--gemini-dir`; the
profile is passed as `ANTIGRAVITY_APP_DATA_DIR={acp_home}` instead, which is
why an entry override must keep that variable (or leave `env` unnamed and
inherit it). If `argv[0]` is a wrapper script, the arguments
`-p /usage --output-format json` go to the wrapper, which must forward them to
`agy` unchanged.

## Limitations

- `acp.harden: false` turns the gateway-owned profile off for a custom `agy`
  command; the command then runs as written and can re-enable host tools, at
  the operator's own risk.
- ACP turns carry no sampling parameters; those settings are reported as
  dropped conversion warnings.
- Google may suspend an account used outside Antigravity's own client. Use an
  account you can afford to lose.
