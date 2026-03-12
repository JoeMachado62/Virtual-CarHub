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
- WordPress/Motors export endpoint:
  - JSON: `GET /v1/inventory/wordpress/export?format=json`
  - CSV: `GET /v1/inventory/wordpress/export?format=csv`
  - Set `PUBLIC_WEB_BASE_URL` to control generated VDP links.
  - Optional auth: set `WORDPRESS_EXPORT_BEARER_TOKEN` and send `Authorization: Bearer <token>`.
- GHL-first e-sign path is supported via document template send (`/proposals/templates/send`) using:
  - `GHL_DOCUMENTS_ENABLED=true`
  - `GHL_RETURN_AUTHORIZATION_TEMPLATE_ID=<template_id>`
- Prometheus metrics are exposed at `/metrics` when `METRICS_ENABLED=true`.

## DB + Storage Ops

- Postgres backup:
  - `bash scripts/db/backup_postgres.sh`
- Postgres restore:
  - `bash scripts/db/restore_postgres.sh /path/to/backup.dump`
- SQLite -> Postgres migration utility:
  - `cd backend && .venv/bin/python scripts/migrate_sqlite_to_postgres.py --sqlite-path ./virtual_carhub.db --truncate-target`
- Alembic uses `DATABASE_URL` when present in environment (no longer forced to sqlite from `alembic.ini`).
- Object storage URL resolution supports:
  - `OBJECT_STORAGE_PUBLIC_BASE_URL`
  - `AWS_CLOUDFRONT_DOMAIN`
  - `S3_ASSETS_BUCKET` + `AWS_REGION` (+ optional `AWS_S3_ENDPOINT_URL`)
