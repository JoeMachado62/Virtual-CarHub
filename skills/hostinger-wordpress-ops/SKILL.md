---
name: hostinger-wordpress-ops
description: Operate Hostinger Cloud and Hostinger WordPress environments using Hostinger API CLI, Hostinger API MCP server, and Hostinger API references. Use for tasks such as authenticating Hostinger API access, listing/managing sites, domains, DNS, backups, and deployment operations across one or more Hostinger WordPress installs with explicit safety checks and guarded write actions.
---

# Hostinger WordPress Ops

## Overview

Use this skill to perform repeatable and safe Hostinger operations from a terminal-driven workflow. Keep account access secure, confirm target environment before changes, and guard mutating commands.

## Quick Start

1. Run `scripts/validate_hostinger_env.sh`.
2. If repos are missing, run `scripts/bootstrap_hostinger_repos.sh`.
3. Read `references/setup.md` for authentication and tool wiring.
4. Read `references/workflows.md` for task patterns.
5. Execute potentially mutating commands through `scripts/hostinger_command_guard.sh`.

## Workflow

### 1. Establish Tooling

Run environment validation first:

```bash
scripts/validate_hostinger_env.sh
```

If repositories are not present, bootstrap:

```bash
scripts/bootstrap_hostinger_repos.sh
```

### 2. Authenticate Safely

Load API tokens only from environment variables, never hardcode them in scripts or command history.

Preferred variables:

- `HOSTINGER_API_TOKEN`
- `HOSTINGER_TOKEN`

Fallback aliases:

- `H_PANEL_API_TOKEN`
- `HOSTINGER_ACCESS_TOKEN`

### 3. Choose Read vs Write Path

- Read-only tasks (list, describe, get, inspect): run directly once target is confirmed.
- Write tasks (create, update, delete, attach, detach, reset, rotate): run through guard script first.

Guarded execution pattern:

```bash
HOSTINGER_ALLOW_WRITE=1 scripts/hostinger_command_guard.sh -- <your-hostinger-command>
```

### 4. Validate Outcome

After each write operation:

1. Re-run the relevant read-only query.
2. Confirm target site/domain/state values changed as expected.
3. Record timestamp, command, and result summary in your project notes.

## Safety Rules

- Refuse write actions when target account/site is ambiguous.
- Require explicit environment confirmation for production changes.
- Avoid broad bulk mutations unless explicitly requested.
- Redact tokens from logs and shared outputs.
- Prefer reversible steps and checkpoint verification.

## References

- `references/setup.md`: repo layout, environment variables, bootstrap guidance.
- `references/workflows.md`: common operation flows and decision points.
- `references/security.md`: token handling and production safety controls.

## Scripts

- `scripts/validate_hostinger_env.sh`: local prereq and environment checks.
- `scripts/bootstrap_hostinger_repos.sh`: clone/update Hostinger repositories.
- `scripts/hostinger_command_guard.sh`: block unsafe mutating commands unless explicitly enabled.
