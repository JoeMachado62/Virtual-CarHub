# Hostinger Security Reference

## Token Handling

- Store tokens only in environment variables or secret managers.
- Never commit tokens to git.
- Never paste tokens into chat or terminal logs that may be shared.
- Redact token values in outputs and screenshots.

## Write Protection

- Default to read-only discovery commands.
- Use explicit write unlock (`HOSTINGER_ALLOW_WRITE=1`) only for intended operations.
- Revert `HOSTINGER_ALLOW_WRITE` to `0` after change execution.

## Production Safety

- Require explicit target confirmation before each production write.
- Avoid combined/bulk operations unless requested.
- Perform post-change verification with independent read queries.
- Keep an operation log with:
  - target site
  - command
  - timestamp
  - verification result

## Incident Guardrails

- If command output is unexpected, stop and inspect before next step.
- If target mismatch is suspected, stop immediately and re-run discovery flow.
- Prefer reversible operations when possible.
