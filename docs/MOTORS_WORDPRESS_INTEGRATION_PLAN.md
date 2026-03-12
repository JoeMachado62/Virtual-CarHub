# Motors + Virtual-CarHub Integration Plan

## Objective
Use a WordPress dealer theme for speed on front-end UX while keeping Virtual-CarHub backend as the source of truth for inventory merge logic, auction overrides, and image pipeline decisions.

## Current Status
- Inventory API already enforces source priority where `auction` data overrides `marketcheck` data.
- New backend export endpoint is available:
  - `GET https://app.virtualcarhub.com/v1/inventory/wordpress/export?format=json`
  - `GET https://app.virtualcarhub.com/v1/inventory/wordpress/export?format=csv`
- Export includes filters and pagination compatible with listing sync workflows.

## Export Contract (Implemented)
- Endpoint: `https://app.virtualcarhub.com/v1/inventory/wordpress/export`
- DNS/TLS prerequisite: `app.virtualcarhub.com` must resolve to `168.231.71.194` with a valid Let's Encrypt certificate on this VPS.
- Formats:
  - `format=json` returns `{ status, data, error }`
  - `format=csv` returns downloadable CSV
- Query params:
  - `q, make, model, trim, body_type, source_type, state`
  - `min_price, max_price, min_year, max_year, min_dom, max_dom`
  - `has_images, include_unavailable, updated_since`
  - `sort_by (updated_at|price|year|mileage), sort_dir (asc|desc)`
  - `page, per_page`
- Key fields returned per listing:
  - `external_id` (VIN), `title`, `slug`, `price`, `mileage`, `images`, `thumbnail`
  - `fuel_type`, `transmission`, `drivetrain`, colors, ownership/title flags
  - `source_type`, `source_priority`
  - `vdp_url` (`https://virtualcarhub.com/vinventory/{vin}`)

## Motors Implementation Approach
1. Install Motors in WordPress and use a child theme for all customizations.
2. Use WP All Import (or custom REST pull) to ingest `format=csv` export from Virtual-CarHub.
3. Map Virtual-CarHub fields to Motors listing fields (VIN, price, mileage, make/model/trim, images, features).
4. Configure incremental sync by `updated_since` so imports only process changed vehicles.
5. Keep Virtual-CarHub API as the canonical inventory source; WordPress is a presentation layer.

## Auction-Override Rule
- Do not merge in WordPress.
- Merge only in Virtual-CarHub backend.
- WordPress receives already-resolved listing data from export endpoint.
- `source_priority` is exposed for transparency and debugging.

## Image Pipeline Alignment
- Current export uses resolved gallery/hero images from Virtual-CarHub display context.
- As auction image pipeline matures, WordPress import will automatically receive updated image URLs through the same export.

## Next Execution Steps
1. Upload Motors theme zip into the project workspace so child-theme overrides can be implemented and versioned.
2. Stand up a WordPress instance (`staging.virtualcarhub.com`) for import and template mapping.
3. Implement importer job (cron/manual) against `https://app.virtualcarhub.com/v1/inventory/wordpress/export?format=csv`.
4. Build Motors child-theme templates for inventory archive and VDP UI parity with current brand.
5. Add smoke tests for import freshness and VDP rendering parity.
