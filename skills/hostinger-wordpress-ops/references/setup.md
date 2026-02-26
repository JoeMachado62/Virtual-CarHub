# Hostinger Setup Reference

## Repository Sources

- `https://github.com/hostinger/api-cli`
- `https://github.com/hostinger/api-mcp-server`
- `https://github.com/hostinger/api`

## Expected Local Layout

Default root: `$HOME/.cache/hostinger-tools` (override with `HOSTINGER_TOOL_ROOT`)

- `$HOSTINGER_TOOL_ROOT/api-cli`
- `$HOSTINGER_TOOL_ROOT/api-mcp-server`
- `$HOSTINGER_TOOL_ROOT/api`

## Bootstrap

```bash
scripts/bootstrap_hostinger_repos.sh
```

## Environment Variables

Primary token variables:

- `HOSTINGER_API_TOKEN`
- `HOSTINGER_TOKEN`
- `HAPI_API_TOKEN`

Fallback aliases:

- `H_PANEL_API_TOKEN`
- `HOSTINGER_ACCESS_TOKEN`

Optional:

- `HOSTINGER_TOOL_ROOT`: override clone location.
- `HOSTINGER_ALLOW_WRITE`: set to `1` only for intentional mutating operations.

Shell loading note:

- For automation/non-interactive commands, put token exports in `~/.profile` or `~/.bash_profile`.
- `~/.bashrc` often returns early in non-interactive shells, so variables defined there may not be visible.

## Tooling Validation

```bash
scripts/validate_hostinger_env.sh
```

## Notes

- Install dependencies per each repo README after clone.
- Resolve exact CLI flags/subcommands from the local README and examples because versions may change.
