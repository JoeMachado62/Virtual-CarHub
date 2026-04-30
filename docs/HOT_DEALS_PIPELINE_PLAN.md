# Hot Deals Pipeline Plan

## Goal

Create a first-class VirtualCarHub Hot Deals feed powered by the OVE
`VHC Marketing List`.

The scraper already does the expensive work:

- Finds OVE vehicles priced at least `$1,000` below MMR.
- Runs deep detail/condition-report scraping.
- Filters out vehicles with negative condition-report signals.
- Produces a small, curated marketing list suitable for social posts.

The VPS should ingest that curated output into a dedicated Hot Deals data
model, reuse the existing VDP/OVE detail flow, and gate condition reports
to admins and credit-approved buyers.

## Why This Is Better Than Global Deal Scoring

Global "best deal" sorting requires reliable MMR for every searchable
vehicle. Current inventory does not have that. The Hot Deals list already
has a trusted business rule and a human/agent-quality screen:

```text
OVE VHC Marketing List -> at least $1,000 below MMR -> deep CR scrape -> negative CR filter -> publishable hot deal
```

This makes Hot Deals a curated acquisition product rather than a broad
search sort.

## Proposed Backend Endpoint

Base path:

```text
POST /api/v1/inventory/ove/hot-deals/ingest
```

Auth:

```text
Authorization: Bearer <SERVICE_TOKEN>
```

Behavior:

1. Validate the batch.
2. Upsert each vehicle into `vehicles`.
3. Upsert the deep scrape payload into `ove_vehicle_details`.
4. Upsert one row per VIN into a new `hot_deals` table.
5. Mark previous active hot deals from the same source/batch scope inactive
   if they are not included in the new full snapshot.
6. Return counts: inserted, updated, expired, rejected, and active.

The endpoint should support both:

- `snapshot_mode = "full_replace"` for the current active VHC Marketing List.
- `snapshot_mode = "append"` for one-off additions/manual recovery.

## New Table

Suggested table: `hot_deals`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid/string | Primary key |
| `vin` | string(17) | FK to `vehicles.vin`, indexed |
| `source_platform` | string | Usually `manheim` |
| `source_list_name` | string | `VHC Marketing List` |
| `batch_id` | string | Scraper batch/run id |
| `snapshot_mode` | string | `full_replace` or `append` |
| `listing_id` | string/null | OVE listing id if available |
| `listing_url` | string/null | OVE listing/detail URL |
| `auction_start_at` | timestamptz/null | OVE listing start time |
| `auction_end_at` | timestamptz | OVE listing end time; required for active display |
| `mmr_value` | numeric | Required |
| `asking_price` | numeric | Required |
| `deal_delta` | numeric | `mmr_value - asking_price`; positive is better |
| `deal_delta_pct` | numeric/null | Optional |
| `deal_label` | string | Example: `Excellent`, `Great` |
| `deal_rank` | int | Lower is better; useful for sorting |
| `cr_screen_status` | string | `passed`, `rejected`, `needs_review` |
| `cr_screen_reasons` | json | Negative-signal filter output |
| `marketing_title` | string/null | Optional social title |
| `marketing_summary` | text/null | Optional short copy |
| `hero_image_url` | string/null | Preferred card image |
| `is_active` | bool | Search/homepage visibility |
| `featured_until` | timestamptz/null | Optional "Deal of the Hour" window |
| `expires_at` | timestamptz | Usually auction/listing end time |
| `payload_json` | json | Raw scraper hot-deal metadata |
| `created_at` | timestamptz | Standard |
| `updated_at` | timestamptz | Standard |

Indexes:

- `(is_active, expires_at)`
- `(is_active, deal_rank, deal_delta DESC)`
- `(vin)`
- `(batch_id)`
- Partial unique active deal per VIN:
  - `UNIQUE (vin) WHERE is_active IS TRUE`

## Active/Expired Rules

A hot deal is active only when:

- `is_active = true`
- `expires_at > now()`
- linked `vehicles.available = true`
- `cr_screen_status = "passed"`

When a new full snapshot arrives:

- VINs in the snapshot are upserted active.
- Active Hot Deals from `source_list_name = "VHC Marketing List"` that are
  missing from the snapshot are set inactive.
- Expired deals are hidden automatically and can be pruned later.

## Condition Report Gating

Hot Deals should reuse existing condition report storage, but response
visibility must be explicit.

Public users can see:

- Vehicle basics
- Price
- MMR delta
- Hot Deal badge
- "Inspection screened" status
- Sanitized highlights

Admins and credit-approved logged-in users can see:

- Full `condition_report`
- CR document page
- Original Manheim/liquidmotors CR URL, if allowed
- Deep scrape images/details

Recommended API pattern:

- Keep `/inventory/{identifier}` public-safe by redacting gated CR fields
  unless authorized.
- Add or reuse a protected CR endpoint for full report:

```text
GET /api/v1/inventory/{vin}/condition-report
```

Authorization should use the existing rules:

- admin: allowed
- logged-in buyer with credit/preapproval status: allowed
- otherwise: denied or redacted

## Frontend

Homepage section:

- Replace "Wholesale Opportunities" with "Deal of the Hour".
- Use `GET /api/v1/hot-deals/active?limit=12` or equivalent.
- Feature the top deal in a stronger treatment.
- Show a scrollable list of remaining deals.
- Use a distinct Hot Deals visual treatment, but keep the section consistent
  with the current VCH design system.

Card fields:

- Image
- Year/make/model/trim
- Price
- State/pickup location
- `Excellent Deal` / `Great Deal`
- `$X below MMR`
- Countdown clock anchored in the lower-left corner, driven by `auction_end_at`
- CTAs: `View Deal`, `Save`

VDP:

- Reuse current VDP structure.
- Add Hot Deal mode when an active `hot_deals` row exists for the VIN.
- Use a dedicated Hot Deals VDP background image/backdrop behind the vehicle
  overlays so these listings are visually distinct from standard VDP pages.
- Keep the vehicle imagery and information overlays in the same general VDP
  layout, but switch the page-level background, accent treatment, and urgency
  styling when `hot_deal.is_active = true`.
- Show urgency using a lower-left countdown clock driven by `auction_end_at`.
- Gate CR details as above.

Hot Deal VDP background requirements:

- Add a configurable/static asset such as
  `/assets/images/hot-deals/hot-deal-vdp-bg.webp`.
- Use that asset only for active Hot Deal VDPs.
- The background should support readable overlays on desktop and mobile.
- The vehicle image, price panel, CTA area, and countdown clock must remain
  legible over the Hot Deals background.
- If the Hot Deal expires, the VDP should fall back to the standard background
  or show an expired-deal state.

Countdown behavior:

- Show `Ends in HH:MM:SS` while more than one hour remains.
- Show `Final minutes MM:SS` under one hour.
- Show `Ending now` under one minute.
- Hide or mark expired once `auction_end_at <= now()`.
- The countdown must be rendered from server-provided UTC timestamps and
  updated client-side once per second.
- If `auction_end_at` is missing, do not show the listing as a Hot Deal.

## Implementation Phases

1. Add database migration and model for `hot_deals`.
2. Add Pydantic schemas for Hot Deals batch ingest.
3. Add `POST /api/v1/inventory/ove/hot-deals/ingest`.
4. Upsert `vehicles`, `ove_vehicle_details`, and `hot_deals` in one transaction.
5. Add active Hot Deals read endpoint.
6. Add CR redaction/gating check to VDP/detail responses.
7. Build homepage Hot Deals section.
8. Add Hot Deal visual mode to VDP.
9. Add cleanup job for expired inactive deals.
10. Add tests for ingest, full replace, expiration, CR gating, and homepage query.

## Open Decisions

- Exact credit-approved flag to use for CR access.
- Whether expired Hot Deals should stay visible to admins.
- Whether social media copy should be stored in `hot_deals` or generated
  separately from the same payload.
- Whether one VIN can have multiple historical hot-deal rows, or whether
  history should live only in `payload_json`/audit events.
