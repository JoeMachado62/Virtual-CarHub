# Virtual-CarHub Cutover Audit

Date: 2026-03-12

## Current Runtime State

- Active old app process:
  - PM2 process `paf-mission-dashboard`
  - Script: `/var/www/paf-ghl/server.js`
  - CWD: `/var/www/paf-ghl`
  - Port: `3002`
- Active new Virtual-CarHub stack:
  - Docker Compose project rooted at `/var/www/paf-ghl/Virtual-CarHub`
  - Frontend: `127.0.0.1:3004`
  - Backend API: `127.0.0.1:8000`
  - Observability: Grafana `3001`, Prometheus `9090`, Loki `3100`
  - Data services: Postgres `15432`, Redis `16379`

## Current Proxy State

- `/etc/nginx/sites-available/virtualcarhub.com`
  - `/` -> `http://localhost:3004`
  - `/api/vch/` -> `http://localhost:8000/v1/`
  - `/mission/` -> `http://localhost:3002/mission/`
- `/etc/nginx/sites-available/app.virtualcrhub.com`
  - `/v1/` -> `http://127.0.0.1:8000/v1/`
  - Next.js route groups -> `http://127.0.0.1:3004`
  - Legacy PAF API `/api/` -> `http://127.0.0.1:3002/api/`
  - Legacy PAF HTML pages like `/dashboard.html` -> `http://127.0.0.1:3002`
  - Legacy mission dashboard `/mission/` -> `http://127.0.0.1:3002/mission/`

## Repo Boundary State

- `/var/www/paf-ghl` is still an active Git repo and still hosts the old Node/Express app.
- `/var/www/paf-ghl/Virtual-CarHub` is a separate Git repo:
  - Remote: `git@github.com:JoeMachado62/Virtual-CarHub.git`
- The old repo still sees `Virtual-CarHub/` as an untracked nested directory.
- This nesting is the main filesystem-level source of confusion and must be removed.

## Canonical Project To Keep

The following should remain the only active codebase after cutover:

- `/var/www/virtual-carhub`
  - `backend/`
  - `frontend/`
  - `monitoring/`
  - `scripts/`
  - `wordpress/`
  - `docs/`
  - `docker-compose.yml`
  - `Makefile`
  - `README.md`
  - `VirtualCarHub_PRD_v2.md`

## Port Before Removing Old PAF Tree

These are the only old-project assets worth intentionally carrying forward.

### Keep as behavior or reference, not as a second codebase

- `/var/www/paf-ghl/config/ghlCustomFieldMap.json`
  - Reason: large GHL custom-field map that may still be needed if VCH restores detailed field sync for credit apps or deal records.
  - Action: port into VCH only if detailed custom-field sync remains a real requirement.

- `/var/www/paf-ghl/services/ghlSubaccountService.js`
  - Reason: contains the per-dealer location fallback strategy:
    - dedicated dealer location if active
    - shared agency location fallback
  - Action: reimplement in VCH only if per-dealer GHL subaccounts remain in scope.

- `/var/www/paf-ghl/routes/applicationRoutes.js`
  - Reason: working reference for old credit application submission, deal-jacket shaping, and conversation-note workflows.
  - Action: do not keep this code live. Use only as a migration reference if those workflows are rebuilt in VCH.

- `/var/www/paf-ghl/services/databaseService.js`
  - Reason: reference for legacy application/conversation persistence model.
  - Action: archive only. Do not reuse the JSON-file storage model.

## Delete From Virtual-CarHub During Cutover

These files are copied legacy PAF portal pages or duplicate static pages that should not remain in the canonical VCH app unless they are actively reimplemented against the VCH `/v1` API.

### Delete now

- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/admin-application-detail.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/admin-dashboard.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/application-details.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/auth-debug.js`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/client-apply.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/client-dashboard.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/credit_application.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/dashboard.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/deal-jacket.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/extension-install.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/forgot-password.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/login.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/premium-dashboard.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/premium-marketing.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/register.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/reset-password.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/submission-tracker.html`

### Delete after confirming Next.js equivalents are the chosen path

- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/about.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/calculator.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/contact.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/index.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/index-two-base.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/inventory.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/vinventory.html`
- `/var/www/paf-ghl/Virtual-CarHub/frontend/public/vinventory-details.html`

Reason:

- These files overlap with the real Next.js app under `frontend/app/`.
- Several still contain Pinnacle branding or old route assumptions.
- Keeping both static and Next.js versions invites further drift.

## Archive Only, Then Remove From VPS

Once VCH is relocated and the proxy/runtime cutover is complete, archive then remove the entire old tree:

- `/var/www/paf-ghl`

That includes these old-only areas:

- `config/`
- `data/`
- `middleware/`
- `public/`
- `routes/`
- `services/`
- `uploads/`
- `chrome-extension/`
- old Node scripts, test files, and dashboard docs

## Immediate Cutover Tasks

1. Move `Virtual-CarHub` out of the old tree to `/var/www/virtual-carhub`.
2. Update all hard-coded `/var/www/paf-ghl/Virtual-CarHub` references inside VCH docs and scripts.
3. Remove copied legacy PAF pages from `frontend/public`.
4. Replace nginx references to old `3002` routes.
5. Stop and remove PM2 process `paf-mission-dashboard`.
6. Archive `/var/www/paf-ghl` to a tarball outside the active app path.
7. Remove `/var/www/paf-ghl` from the VPS after final verification.
