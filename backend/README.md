# Virtualo Car Hub Backend

FastAPI implementation of the VirtualCarHub PRD v2 API surface.

## Local Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

## API Docs

- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Notes

- External integrations (GHL, MarketCheck, lender APIs) are implemented as adapters with safe stubs for local mode.
- All endpoints use a standard envelope: `{ status, data, error }`.
- Rate limits follow PRD defaults (`BUYER_RATE_LIMIT_PER_MINUTE=100`, `AGENT_RATE_LIMIT_PER_MINUTE=1000`) with Redis-backed or in-memory fallback.
- Existing Pinnacle env names are supported (for example `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `GHL_DEALS_STAGE_NEW` fallback aliases).
- GHL-first e-sign path is supported via document template send (`/proposals/templates/send`) using:
  - `GHL_DOCUMENTS_ENABLED=true`
  - `GHL_RETURN_AUTHORIZATION_TEMPLATE_ID=<template_id>`
- Prometheus metrics are exposed at `/metrics` when `METRICS_ENABLED=true`.
