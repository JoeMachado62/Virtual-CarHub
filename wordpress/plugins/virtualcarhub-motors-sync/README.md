# VirtualCarHub Motors Sync Plugin

This plugin imports inventory rows from the VirtualCarHub backend export API into Motors listing posts.

## What it does

- Pulls paginated inventory data from `GET https://app.virtualcarhub.com/v1/inventory/wordpress/export?format=json`.
- Upserts listings by VIN (`vin_number` meta) into the configured Motors post type (default: `listings`).
- Maps core listing fields (price, VIN, mileage, location, features, source metadata).
- Maps Motors attribute/taxonomy options from `stm_vehicle_listing_options`.
- Syncs featured image + gallery from API image URLs (with URL fingerprint dedupe).
- Configurable image controls:
  - `Image Sync Mode`:
    - `External URLs only (fastest)` (recommended for production scale)
    - `Download featured image only`
    - `Download featured + gallery`
  - In `External URLs only` mode, single listing (VDP) gallery is rendered from `vch_remote_image_urls_json` with no attachment downloads.
  - `Max Images Per Listing` (`0` means no cap, sync all images returned by API)
  - `Image Download Timeout (sec)` for sideload reliability
- Sets sold flag (`car_mark_as_sold`) for unavailable listings.
- Stores MarketCheck price comparison fields when enabled.
- Supports scheduled sync (WP-Cron) and manual sync from wp-admin.
- Enforces a hard floor: only listings with `days_on_market >= 45` are eligible for publish.
- Includes one-click `Force Full Sync (Reset Checkpoint)` action in wp-admin.
- Includes one-click `Test API Connection` action in wp-admin.
- Includes one-click `Draft Non-Synced Listings` cleanup action to hide leftover demo posts.
- Supports dynamic ZIP/radius request seeding on inventory searches:
  - If a frontend inventory request includes ZIP (`zip_code`, `zipcode`, `zip`, or `postal_code`) and optional radius (`radius`, `distance`, or `miles`), plugin calls backend export with that ZIP and upserts returned rows before query render.
  - This keeps ZIP user-driven (not preset) and works with fallback top-up behavior from backend.
  - Frontend query is constrained to VINs returned by the ZIP/radius seed request (short-lived cache window), so results stay location-relevant without preset ZIPs.
  - ZIP is required for this live API top-up path; if ZIP is missing, plugin skips API search.

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
   - `Image Sync Mode` (`External URLs only` recommended for high traffic).
   - `Max Images Per Listing` (`0 = all images`).
   - `Image Download Timeout (sec)`.
   - `Cron Interval`.
4. Click `Save Sync Settings`.
5. Click `Sync Now` for first load.
6. If demo cards still show, click `Draft Non-Synced Listings` once.
7. If filter dropdowns still contain stale demo values, click `Purge Empty Filter Terms`.

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
- Dynamic ZIP request seeding uses a short request cache window per filter combination to reduce duplicate API pressure.
- For truly reliable scheduling, use system cron hitting `wp-cron.php`.
