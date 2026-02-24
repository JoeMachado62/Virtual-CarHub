# GHL-First Foundation Plan

## Decision

Virtual-CarHub is now aligned to a GHL-first operational model for MVP execution speed:
- CRM, opportunities, communication, automation, e-sign workflows in GHL.
- High-volume matching/inventory analytics remain in Postgres.

## Why this split

- GHL excels at workflow automation, pipeline orchestration, contacts, tasks, comms, and human operations.
- Postgres is better for 50K+ inventory records, BFV scoring, and analytics-heavy workloads.

## Custom Objects Strategy

### Recommended for MVP (yes)

- `loan_cases`
  - Fields: deal_id, lender_name, funding_state, apr, term, approval_amount, stip_count
  - Purpose: single source of operational loan status for ops users

- `return_cases`
  - Fields: deal_id, vin, return_reason, return_state, initiated_at, refund_amount, dispute_flag
  - Purpose: operational return queue and SLA tracking

- `shipments`
  - Fields: deal_id, vin, carrier_name, tracking_url, eta, status
  - Purpose: delivery status visibility in GHL workspace

### Recommended with constraints (partial)

- `vehicles`
  - Use for selected + shortlist vehicles only, not full market inventory mirror.
  - Fields: vin, year, make, model, trim, price_asking, selected_flag, match_score, deal_id

### Not recommended for MVP (too ambitious)

- Full DMS replacement entirely inside GHL custom objects with full title/reg/accounting/compliance logic.
- Full 50K inventory catalog as custom object records.

## Phased rollout

1. Phase A: GHL-first docs + lifecycle sync (in progress)
2. Phase B: `loan_cases` + `return_cases` custom object records
3. Phase C: shortlist `vehicles` custom object sync
4. Phase D: evaluate deeper DMS modules based on deal volume and SLA pressure

## Guardrails

- Keep VCH backend as source of truth for computational state and audit/event history.
- Use idempotent sync patterns from VCH -> GHL (retry + reconciliation).
- Avoid hard-coding pipeline/stage IDs; load from env/config only.
