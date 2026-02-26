# Hostinger Workflow Reference

## Read-Only Discovery Flow

1. Validate env and repos:
   - `scripts/validate_hostinger_env.sh`
2. Inspect account/site scope with read commands.
3. Confirm target identifiers:
   - account
   - project/site
   - domain/subdomain
4. Save the target identifiers before any write step.

## Mutating Change Flow

1. Perform full discovery flow first.
2. Prepare the exact command.
3. Execute through guard:

```bash
HOSTINGER_ALLOW_WRITE=1 scripts/hostinger_command_guard.sh -- <command ...>
```

4. Re-run corresponding read query to verify state.
5. Log command + outcome + timestamp.

## WordPress Site Enablement Flow

1. Confirm target WordPress site/container in Hostinger.
2. Install/activate required plugins and parent theme in WP admin.
3. Upload and activate child theme package.
4. Validate pages, menu, and permalink configuration.
5. Validate inventory integration endpoints from the WordPress environment.

## Multi-Site Operations Flow

1. Require explicit site identifier in every command.
2. Avoid global commands that affect multiple sites.
3. Execute one site change at a time.
4. Verify each site independently after changes.
