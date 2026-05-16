# Pinnacle Reuse Audit (GHL + Env)

## Reused in Virtual-CarHub

- Existing GoHighLevel env keys and values are consumed directly:
  - `GHL_API_KEY`, `GHL_API_BASE_URL`, `GHL_API_VERSION`, `GHL_LOCATION_ID`, `GHL_WEBHOOK_SECRET`
  - `GHL_DEALS_PIPELINE_ID` and stage IDs
  - `GHL_COMPANY_ID`, `GHL_AGENCY_API_KEY`/`HL_AGENCY_API_KEY`, `GHL_PRIVATE_TOKEN`
- Existing auth/env conventions are supported:
  - `JWT_SECRET_KEY` (fallback-compatible JWT timing names)
  - `ALLOWED_ORIGINS` mapped into `CORS_ORIGINS`
  - `API_SECRET_KEY` reused as `SERVICE_TOKEN` if no dedicated service token exists
- Existing GHL workflow patterns reused:
  - Contact-first approach, then opportunity creation
  - Dynamic stage updates tied to lifecycle transitions
  - High-priority task creation on return/exception state

## GHL integration behavior now in Virtual-CarHub

- On deal state transition, backend attempts to:
  1. Ensure a GHL contact exists.
  2. Ensure a GHL opportunity exists in configured pipeline.
  3. Update opportunity stage based on PRD lifecycle state.
  4. Add a timeline note to contact.
- Webhook auth hardening added:
  - GHL endpoint supports HMAC signature verification when `GHL_WEBHOOK_SECRET` is set.

## Useful assets discovered in Pinnacle project

- `config/ghlCustomFieldMap.json` provides a large custom-field ID map that can be used for future detailed field sync.
- `services/ghlSubaccountService.js` contains a practical location fallback strategy:
  - Dedicated dealer location if active
  - Shared agency location fallback

## Risks/gaps observed in Pinnacle code (for awareness)

- Inconsistency in stage env naming between config and service expectations (`*_NEW` vs `*_NEW_DEAL_SUBMITTED`).
- `routes/applicationRoutes.js` references `ghlApiService.createContact/createOpportunity/addContactNote`; current exported names in `services/ghlApiService.js` differ (`createGhlContact/createGhlOpportunity/...`).
- GHL webhook signature verification in Pinnacle route is marked TODO and not fully implemented.
