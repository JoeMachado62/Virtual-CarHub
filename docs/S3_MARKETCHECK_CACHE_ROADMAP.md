# S3 MarketCheck Cache Roadmap

## Current State (as of 2026-02-26)

- VirtualCarHub persists normalized inventory rows in the `vehicles` table.
- Image source references are persisted in `vehicle_image_assets` and related image-job tables.
- There is no AWS S3 client integration in backend runtime code yet.
- There is no object-store cache layer that serves MarketCheck payloads by VIN.

## Decision for now

- Keep current behavior (live MarketCheck calls where configured).
- Rely on existing DB persistence for baseline reuse.
- Defer S3 payload cache until traffic/cost warrants it.

## Why this is acceptable short-term

- Inventory ingest already stores normalized listing data locally.
- WordPress sync can run off local export payloads without live sync.
- This keeps architecture simpler while validating listing/VDP UX and conversion flow.

## Gaps to close later

1. VIN-level payload cache for listing detail enrichment.
2. Search/facet payload cache for repeated query shapes.
3. Price stats cache for `include_price_stats=true` exports.
4. Cache freshness policies and invalidation rules.

## Proposed Phase Plan

### Phase 1: Read-through VIN cache

- Add cache lookup before MarketCheck detail calls:
  - Key: `marketcheck/vin/{vin}/latest.json`
  - Metadata: `fetched_at`, `ttl_seconds`, `source_endpoint`, `listing_id`
- On cache miss or stale object:
  - Call MarketCheck
  - Store raw payload in S3
  - Return payload
- Suggested TTL:
  - detail payloads: 6-24 hours

### Phase 2: Query-shape cache

- Add cache for expensive repeated calls:
  - facets queries
  - filtered search result pages
- Key pattern:
  - `marketcheck/query/{sha256(canonical_query)}.json`
- Suggested TTL:
  - facets: 1-6 hours
  - search pages: 15-60 minutes

### Phase 3: Price stats cache

- Cache per VIN price stats used by WordPress export:
  - Key: `marketcheck/price/{vin}.json`
- Suggested TTL:
  - 24 hours

### Phase 4: Cache observability + controls

- Add metrics:
  - hit/miss rate by operation
  - stale refresh count
  - API calls avoided
  - estimated cost savings
- Add admin toggles:
  - `MARKETCHECK_CACHE_ENABLED`
  - `MARKETCHECK_CACHE_TTL_*`
  - `MARKETCHECK_CACHE_FORCE_REFRESH`

## Suggested backend config additions

- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `S3_MARKETCHECK_CACHE_BUCKET`
- `MARKETCHECK_CACHE_ENABLED=true|false`
- `MARKETCHECK_CACHE_TTL_DETAIL_SECONDS`
- `MARKETCHECK_CACHE_TTL_SEARCH_SECONDS`
- `MARKETCHECK_CACHE_TTL_FACETS_SECONDS`
- `MARKETCHECK_CACHE_TTL_PRICE_SECONDS`

## Data safety notes

- Do not store secrets in cached payloads.
- Prefer server-side encryption at rest for S3 objects.
- Apply lifecycle rules to expire short-lived query caches.
- Keep immutable audit/event logs separate from ephemeral API caches.

## Implementation priority recommendation

1. VIN detail cache
2. Price stats cache
3. Query-shape cache
4. Metrics + tuning

This order gives the fastest cost reduction with lowest complexity.
