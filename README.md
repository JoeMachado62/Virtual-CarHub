# Virtual-CarHub

Greenfield implementation of the `VirtualCarHub_PRD_v2.md` in a standalone project root.

## Project Layout

- `backend/` FastAPI API, SQLAlchemy models, Celery task scaffolding, PRD route map
- `frontend/` Next.js buyer dashboard and admin workspace MVP
- `docs/` PRD coverage and implementation notes

## Quick Start (Local)

```bash
cd /var/www/paf-ghl/Virtual-CarHub
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.seed
uvicorn app.main:app --reload --port 8000

# Frontend (new shell)
cd ../frontend
npm install
npm run dev
```

Frontend: `http://localhost:3000`
Backend docs: `http://localhost:8000/docs`
Grafana: `http://localhost:3001` (admin/admin, when running with Docker Compose)
Prometheus: `http://localhost:9090`
Loki: `http://localhost:3100`

## Demo Credentials

- Email: `buyer@example.com`
- Password: `BuyerPass123!`
- Service token: `dev-service-token`

## Scope Notes

- External integrations (MarketCheck, GHL, lender APIs) are adapter-backed and safe-stubbed for local usage.
- Core lifecycle, matching, return flow, audit trail, feature flags, and route map are implemented.
- Existing Pinnacle portal env conventions are supported for GHL/JWT compatibility. See `docs/PINNACLE_REUSE_AUDIT.md`.

## Monitoring Stack (Open Source)

The project now supports an OSS observability stack:
- Metrics: Prometheus scraping backend `/metrics`
- Logs: Loki + Promtail (backend rotating file logs)
- Dashboards: Grafana with pre-provisioned datasource and overview dashboard

Start all services:
```bash
docker compose up -d
```
