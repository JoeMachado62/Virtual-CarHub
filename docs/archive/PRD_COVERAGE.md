# PRD Coverage Matrix (MVP Implementation)

## Implemented Directly

- Section 3 state machine with transition guards and audit logging
- Section 4 modules covered in MVP scope:
  - Quick Match, profile persistence, BFV storage
  - Vehicle inventory schema and ingestion stub
  - Matching engine (quick + full profile pathway)
  - Deal Desk data hooks + margin config table
  - Funding, sourcing, logistics, DMS-lite endpoints
  - Client dashboard and Danny chat
  - Return flow (7-day window, refund processing)
- Section 5 canonical data model tables represented in SQLAlchemy models
- Section 6 GHL integration architecture represented via webhook endpoints and adapter layer
- Section 7/8 agent + HITL orchestration primitives via admin/service endpoints + audit events
- Section 17 retry/circuit breaker utility and service policy wrappers
- Section 18 backend REST route map implemented at `/v1/...`
- Section 20/21 return and cancellation primitives with stage-aware transition behavior
- Section 22 feature flags and config hierarchy backed by DB tables
- Section 23 schema management scaffold (`SQLAlchemy + Alembic folder + init seed path`)

## Implemented as Adapters/Stubs (Ready to Swap to Live APIs)

- MarketCheck and MarketCheck Price integration
- GHL API publishing/sync reconciliation
- GHL document template send path for return authorization (`/proposals/templates/send`)
- Optional DocuSign/Telnyx adapters retained for fallback migrations
- Lender soft-pull/funding provider integrations
- Central Dispatch booking/tracking integration

## Not Fully Productized Yet

- Automated auction computer-use agent actions
- Multi-lender waterfall and advanced decisioning
- TikTok catalog feed + Equity Alert automations
- Production infra IaC (AWS ECS/RDS/ElastiCache) and full alert routing hardening
