# Implementation Notes

- API envelope shape: `{ status, data, error }`
- Auth model for local MVP uses JWT in-app (Supabase/Auth provider can replace this adapter in production)
- Feature flags and business config are DB-backed (`feature_flags`, `config`) and seeded with PRD defaults
- Return flow enforces 7-day window using `deal.delivered_at`
- Return authorization uses GHL document template send path when `GHL_DOCUMENTS_ENABLED=true` and template ID is set
- Seed script creates:
  - Feature flags
  - Config entries
  - Inventory sample vehicles
  - Buyer test account
  - Active and delivered deals for demoing both matching and returns
- Observability stack: Prometheus (`/metrics`) + Grafana + Loki/Promtail via Docker Compose
