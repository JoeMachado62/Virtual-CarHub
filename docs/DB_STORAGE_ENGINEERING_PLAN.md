# VirtualCarHub DB + Storage Engineering Plan

## Objectives

1. Keep existing API contracts, field names, and model structure stable.
2. Scale inventory/search/VDP reads to hundreds of thousands of listings.
3. Minimize dependency on live third-party API calls in the user request path.
4. Use object storage for media/cache artifacts, not as the primary query database.

## Current runtime status (verified)

- Postgres is running in the stack (`postgres:16`) and backend is pointed to Postgres.
- Active backend DB URL: `postgresql+psycopg://vch:vch@postgres:5432/virtual_carhub`.
- Core table counts are non-zero (`vehicles`, `vehicle_image_assets`, `vehicle_image_jobs`).

## Architecture decision

- Primary transactional/query DB: Postgres.
- Cache/queue/rate controls: Redis.
- Object storage: S3-compatible bucket(s) for media + cache artifacts.
- CDN/public media edge: CloudFront (or storage public base URL).

## Compatibility constraints honored

- Existing table names preserved (`vehicles`, `vehicle_image_assets`, etc.).
- Existing column names preserved (`images`, `features_normalized`, `storage_key`, etc.).
- Existing route payload shapes preserved.
- Storage integration added as URL resolution layer, not schema rewrite.

## Implemented in this pass

1. DB pool tuning support in config/session (non-breaking defaults).
2. S3/object-storage settings added to backend config.
3. Object-storage URL resolver service added.
4. Image pipeline now resolves `storage_key` to public URLs for cards/VDP contexts.
5. Alembic now respects `DATABASE_URL` env override.
6. Postgres performance index migration added (functional + expression indexes for current query style).
7. DB operations scripts added:
   - Postgres backup
   - Postgres restore

## Migration strategy for existing DBs

### A) Postgres -> Postgres (preferred for production moves)

1. Create backup:
   - `bash scripts/db/backup_postgres.sh`
2. Restore into target:
   - `bash scripts/db/restore_postgres.sh /path/to/backup.dump`

## Deployment order

1. Backup Postgres.
2. Deploy backend code with new config/session/storage resolver.
3. Run Alembic to apply performance indexes.
4. Validate inventory/search/VDP endpoints.
5. Move public search paths to DB-only (disable live third-party calls in read path).

## Recommended production next steps

1. Turn `live_sync` off by default on public pages.
2. Shift MarketCheck to scheduled ingest only.
3. Add daily API budget guardrails in backend.
4. Add cached facets/search result materialization for top query shapes.
5. Add S3 lifecycle policies for cached payload objects.
