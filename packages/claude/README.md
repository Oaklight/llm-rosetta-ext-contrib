# claude

Anthropic Claude through the vendor's own CLI. Two shims, one transport:

| Provides | What it is |
|---|---|
| `claude--acp` | The Claude Agent SDK adapter over ACP |
| `claude--messages` | The official Claude Code CLI as a model client, through a loopback relay (`claude_cli` transport) |

Both lanes leave the credential in the CLI's own login store. Sign in on the gateway host with `claude auth login --claudeai`.

Maturity: experimental. Moved here from `llm-rosetta-shim-contrib/providers/claude` and `llm-rosetta-plugins-contrib/plugins/claude-cli`.

## Status of this copy

- `auth.py` still imports `llm_rosetta_shim_contrib._vendor_cli`, which does not exist in this repo. The helper has to move to core or be vendored here (open item in the repo README).
- `tests/test_transport.py` was renamed from the plugin's tests and has not been run here. It needs a core that ships `llm_rosetta.contracts.transport`.
