# VirtualCarHub Motors Sync Plugin

This plugin imports inventory rows from the VirtualCarHub backend export API into Motors listing posts.

## What it does

- Pulls paginated inventory data from `GET /api/vch/inventory/wordpress/export?format=json`.
- Upserts listings by VIN (`vin_number` meta) into the configured Motors post type (default: `listings`).
- Maps core listing fields (price, VIN, mileage, location, features, source metadata).
- Maps Motors attribute/taxonomy options from `stm_vehicle_listing_options`.
- Syncs featured image + gallery from API image URLs (with URL fingerprint dedupe).
- Sets sold flag (`car_mark_as_sold`) for unavailable listings.
- Stores MarketCheck price comparison fields when enabled.
- Supports scheduled sync (WP-Cron) and manual sync from wp-admin.
- Enforces a hard floor: only listings with `days_on_market >= 45` are eligible for publish.
- Includes one-click `Force Full Sync (Reset Checkpoint)` action in wp-admin.
- Includes one-click `Test API Connection` action in wp-admin.

## Admin setup

1. Install and activate the plugin.
2. Open `Tools > VCH Motors Sync`.
3. Configure:
   - `Export Endpoint`: your backend export endpoint.
   - `Bearer Token`: required if backend sets `WORDPRESS_EXPORT_BEARER_TOKEN`.
   - `Listing Post Type`: usually `listings`.
   - `Rows Per Page` and `Max Pages Per Run`.
   - `Include MarketCheck Price Stats` if you want pricing deltas.
   - `Download and Attach Images`.
   - `Cron Interval`.
4. Click `Save Sync Settings`.
5. Click `Sync Now` for first load.

## Backend expectation

The API must return:

- `status=ok`
- `data.items[]`
- `data.pagination.has_next`

The plugin is built to consume the current VirtualCarHub export contract including:

- `vin`, `title`, `slug`, `price`, `mileage`
- `make`, `model`, `trim`, `body_type`, `fuel_type`, `transmission`, `drivetrain`
- `images[]`, `thumbnail`, `available`, `updated_at`
- `image_display_mode`, `inspection_status`, `has_inspection_report`, `photos_coming_soon`
- `marketcheck_average_retail`, `price_delta_marketcheck`, `price_delta_marketcheck_pct`
- `days_on_market`

## Notes

- If your Motors attribute slugs differ from default assumptions, keep them in `stm_vehicle_listing_options`; the plugin uses slug-based mapping heuristics.
- For large catalogs, increase server resources and set a moderate `Rows Per Page` (e.g. 100-200).
- For truly reliable scheduling, use system cron hitting `wp-cron.php`.
