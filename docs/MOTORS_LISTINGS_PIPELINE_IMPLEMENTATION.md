# VirtualCarHub Motors Listings Pipeline (Implementation)

## Goal

Use Motors inventory and single-listing UX while keeping VirtualCarHub backend as the canonical data + image decision layer.

## Implemented components

1. Backend export endpoint enhancements in `backend/app/api/v1/routers/inventory.py`.
2. WordPress sync plugin in `wordpress/plugins/virtualcarhub-motors-sync`.
3. Packaging script in `wordpress/scripts/build_motors_sync_plugin_zip.sh`.

## Data flow

1. `POST /api/v1/inventory/ingest` and/or `GET /api/v1/inventory/search?live_sync=true` ingest/update MarketCheck inventory in backend.
2. Backend source-priority logic enforces merge precedence:
   - `auction` > `dealer_partner` / `dealer_wholesale` > `marketcheck`.
3. WordPress plugin fetches pages from:
   - `GET /api/v1/inventory/wordpress/export?format=json`
   - Plugin enforces `min_dom=45` on export fetch.
4. Plugin upserts Motors listing posts by VIN (`vin_number`).
5. Motors inventory and single-listing pages render from native listing post/meta/taxonomy data.

## Image strategy alignment (spec v2)

The backend export now sends image context fields directly:

- `image_display_mode`
- `inspection_status`
- `has_inspection_report`
- `photos_coming_soon`

Image precedence remains backend-owned:

- If inspection report images are verified, those are exported as primary images.
- Otherwise hero + marketing gallery are exported using Tier-2/Tier-3/source-cache fallback.

This keeps WordPress as presentation-only. The image decision tree and auction override logic stay centralized.

## Pricing comparison support

`/inventory/wordpress/export` now supports:

- `include_price_stats=true`

When enabled and MarketCheck credentials are active, export items include:

- `marketcheck_average_retail`
- `price_delta_marketcheck`
- `price_delta_marketcheck_pct`

The WordPress plugin stores these in listing meta for reporting widgets or dashboards.

## WordPress sync plugin behavior

- Scheduled sync via WP-Cron.
- Manual sync from wp-admin (`Tools > VCH Motors Sync`).
- Forced full sync from wp-admin (resets `updated_since` checkpoint and runs full upsert).
- API connectivity test from wp-admin (checks export endpoint and first-page payload).
- Hard publish floor: only vehicles with `days_on_market >= 45`.
- VIN-based idempotent upsert.
- Sold handling via `car_mark_as_sold` when `available=false`.
- Featured image + gallery sync with URL-fingerprint dedupe.
- Attribute mapping using `stm_vehicle_listing_options` slugs.

## Deployment checklist

1. Build plugin zip:
   - `wordpress/scripts/build_motors_sync_plugin_zip.sh`
2. Upload `wordpress/packages/virtualcarhub-motors-sync.zip` to WordPress and activate.
3. Configure `Tools > VCH Motors Sync`.
4. Run first manual sync.
5. Confirm inventory archive and single listing pages render imported listings.
6. Verify WP-Cron execution cadence.

## Notes

- If your listing post type is not `listings`, set it in plugin settings.
- If custom Motors attribute slugs differ, keep those options defined; plugin slug heuristics will map most common fields.
- For high volume, reduce `per_page` and increase cron frequency.
