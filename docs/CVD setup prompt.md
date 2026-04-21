# ChromeData Image Integration — Coding Agent Briefing

## Objective

Wire up ChromeData's two API products so VirtualCarHub displays professional exterior and interior vehicle images. The system must support two integration paths: a **Media Server path** (working) for browsing-stage stock images, and a **CVD + Media Server path** (blocked on a vendor-side issue, not code) for VIN-exact color-matched images.

## Status Summary (Current)

| Component | Status |
|-----------|--------|
| Chrome Image Gallery / Media Server | ✅ **Working in production** — basic HTTP auth, real image URLs returned |
| Shared-Secret HMAC-SHA1 signing (Tyk protocol) | ✅ **Implemented and verified** — signature matches vendor's published sample |
| VSS (Vehicle Specification Service) auth | ✅ **Authenticating successfully** against `https://vss-api.jdpower.com/VSS/v1.0/years` using the same signing flow — proves the auth implementation is correct end-to-end |
| CVD (VIN Descriptions) auth | ⚠️ **Blocked — vendor-side issue, not code** — all request variants return `403 Forbidden: "Requested endpoint is forbidden"` |

**Open ticket with ChromeData Support** asking whether CVD requires:
1. A separate product entitlement from VSS even with the same portal key/secret
2. A different API key/secret pair
3. A required `profileKey` for production calls
4. A confirmation of the correct production endpoint path
5. A known-good sample request

Until support responds, ship the Media Server path as-is and keep the CVD client code ready but disabled behind the `CHROMEDATA_CVD_ENABLED` flag.

---

## What ChromeData Provides

ChromeData offers two separate API products, each with its own auth mechanism:

### 1. Chrome Image Gallery / Media Server (WORKING)

Serves actual image files. Provides multi-view exterior/interior shots and color-matched exterior images for every vehicle trim from 2010 onward (2001–2010 historical coverage available with fewer angles).

**Auth:** Basic HTTP auth (username + password). Credentials confirmed working.

**Base URL:** `http://media.chromedata.com/MediaGallery/service/`

**Two lookup methods:**

- **By Style ID (preferred):** `GET /style/{styleId}` — returns all image URLs for that exact trim. Includes exact-match flags, carryover flags, and OEM temp flags.
- **By Year/Division/Model/BodyType:** `GET /{Country}/{Year}/{Division}/{Model}/{BodyType}` — crawlable hierarchy. Returns image URLs at the bottom level. Does NOT include exact-match flags.

**Response format:** XML by default, JSON via `.json` suffix. Returns `view` elements (multi-view shots) and `colorized` elements (color-matched shots). Each element contains image URLs with attributes: `shotCode`, `width`, `height`, `backgroundDescription`, `primaryColorOptionCode`, `primaryRGBHexCode`.

**Image sizes available:**
- Small: 320×240 (FTP + Media Server)
- Medium: 640×480 (FTP + Media Server)
- Large: 1280×960 (FTP + Media Server)
- Extra Large: 2100×1575 (Media Server only)

**Backgrounds:** White (JPG) and Transparent (PNG).

**Shot codes (exterior):**
| Code | Description | Gallery Tier |
|------|-------------|-------------|
| 01 | Front ¾, facing left | Basic + Expanded |
| 02 | Rear ¾, facing right | Basic + Expanded |
| 03 | Side profile, facing left | Basic + Expanded |
| 05 | Front (full) | Expanded |
| 06 | Rear (full) | Expanded |
| 07 | Front ¾, facing right | Expanded |

**Shot codes (interior):**
| Code | Description | Gallery Tier |
|------|-------------|-------------|
| 12 | Full dashboard | Basic + Expanded |
| 11 | Driver's dash | Expanded |
| 13 | Driver's side, door open | Expanded |
| 18 | Stereo system | Expanded |
| 24 | Trunk/hatch open | Expanded |
| 25 | Engine | Expanded |
| 28 | Rear seats | Expanded |
| 43 | Center console | Expanded |
| 44 | Passenger dash | Expanded |
| 46 | Navigation system | Expanded |

**Color-matched images** come in 3 angles (front ¾ = code 01, rear ¾ = code 02, side profile = code 03) and are rendered in every available manufacturer paint color. Each colorized element includes the manufacturer paint code (`primaryColorOptionCode`) and RGB hex value.

**Important notes:**
- Exotic, chassis-cab, cutaway, medium-duty, and cargo van vehicles have no color-matched images.
- Images flagged `carryOver=Y` reuse a prior model year's photo for the current year.
- Images flagged `oemTemp=Y` are temporary OEM-provided placeholders.
- The 2100px size is only available via Media Server, not FTP. If you use FTP mapping data, filter out 2100-size rows.

### 2. ChromeData VIN Descriptions / CVD (BLOCKED — 403 Forbidden, vendor-side issue)

Decodes a VIN into full vehicle data including the Chrome `styleId`, exterior color codes, interior colors, features, packages, and tech specs.

**Base URL:** `https://cvd-api.jdpower.com/CVD/v1.0`

**Endpoint (per OpenAPI spec from portal):** `GET /vin/{vin}`

**Auth:** Tyk Shared Secret Security Protocol. This is **NOT** a static token — it is a per-request HMAC-SHA1 signature that must be computed fresh for every single API call. The signature is tied to the `Date` header, so clock drift will cause rejections.

> **Confirmation that our auth implementation is correct:** the same HMAC-SHA1 signing flow successfully authenticates against VSS (`https://vss-api.jdpower.com/VSS/v1.0/years`) and returns valid data. The CVD `403 Forbidden: "Requested endpoint is forbidden"` response is therefore **not a signing problem** — it points to CVD-specific entitlement, route, or profile configuration on the vendor side. Do not modify the signing code while debugging CVD.

#### CVD request variants tested (all return 403 Forbidden)

| Attempted path | Response |
|----------------|----------|
| `GET /vin/{vin}` (per OpenAPI spec) | `403 {"error":"Requested endpoint is forbidden"}` |
| `GET /vindescription/{locale}/{vin}` | `403 {"error":"Requested endpoint is forbidden"}` |
| `GET /vindescription?vin=...&language_Locale=...` | `403 {"error":"Requested endpoint is forbidden"}` |

All three variants used valid HMAC-SHA1 signed headers (same method that works for VSS). The consistent 403 across three different paths strongly suggests the key/secret pair does not have CVD product access, not a routing problem.

#### Likely root causes (awaiting ChromeData Support response)

1. **Separate product entitlement required** — CVD may need to be explicitly enabled on the account even when the portal lists it as an available API.
2. **Different key/secret pair for CVD** — the portal Access tab may show distinct credentials per API product that we're treating as interchangeable.
3. **Required profileKey** — CVD may require a tenant-specific `profileKey` query parameter on every call.
4. **Different production endpoint path** — the OpenAPI spec path (`/vin/{vin}`) may not match the actual production route.

#### Required Request Headers (all four are mandatory)

| Header | Value |
|--------|-------|
| `Accept` | `application/json` |
| `Content-Type` | `application/json` |
| `Date` | RFC 1123 UTC timestamp, e.g. `Thu, 15 May 2025 17:40:21 GMT` |
| `Authtoken` | Signed token (format below) |

#### Authtoken Format

```
Signature keyId="<API_KEY>",algorithm="hmac-sha1",signature="<URL_ENCODED_SIGNATURE>"
```

Note the literal word `Signature` at the start, the comma-separated `key=value` pairs with no spaces after commas, and the double quotes around each value.

#### Signature Generation Algorithm (6 steps)

1. Get the current UTC time as an RFC 1123 string: `Thu, 15 May 2025 17:40:21 GMT`. This **same** string goes in both the `Date` header AND the signing input — they must match exactly.
2. Build the signing input string: `date: <UTC_date_string>` (the literal word `date`, colon, single space, then the date).
3. Compute HMAC-SHA1 of that string using the **API Secret** as the key.
4. Base64-encode the raw HMAC bytes.
5. URL-encode the Base64 string (e.g. `=` becomes `%3D`).
6. Insert into the Authtoken template above.

#### Python Reference Implementation (verified against the PDF's sample)

```python
import hmac
import hashlib
import base64
import urllib.parse
from email.utils import formatdate

def build_cvd_auth_headers(api_key: str, api_secret: str) -> dict:
    # RFC 1123 UTC date (same format as JavaScript's toUTCString())
    date = formatdate(timeval=None, localtime=False, usegmt=True)

    # Signing input — MUST be exactly "date: <date>" with one space
    signing_input = f"date: {date}"

    # HMAC-SHA1 → base64 → URL-encode
    mac = hmac.new(
        api_secret.encode("utf-8"),
        msg=signing_input.encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()
    sig_b64 = base64.b64encode(mac).decode("utf-8")
    sig_encoded = urllib.parse.quote(sig_b64, safe="")

    authtoken = (
        f'Signature keyId="{api_key}",'
        f'algorithm="hmac-sha1",'
        f'signature="{sig_encoded}"'
    )

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Date": date,
        "Authtoken": authtoken,
    }
```

#### Verified Sample from the Security Protocol PDF

Use this as a unit test to confirm the implementation is correct **before** testing against live credentials. I have already verified these inputs produce the exact expected output:

| Input | Value |
|-------|-------|
| API Key | `eyJvcmciOiI2NDI0YTEwNjY2NDU4MDAwMDFmMjk5ODAiLCJpZCI6Ijk3Y2Q0NmE0ZmI1NTQ4Yjk5YzIxYmUxMzgzODgwMDg0IiwiaCI6Im11cm11cjEyOCJ9` |
| API Secret | `ZDRjM2JjMzYwZDdkNGQ3MjgwNWE4N2Q5NTMyOGYxOGE=` |
| Date | `Thu, 15 May 2025 17:40:21 GMT` |
| Expected URL-encoded signature | `nY9NLuyne8IGbo4KHTcIj9DRpi8%3D` |

The production secret and key are **different values** — the above is only for verifying the algorithm.

#### Implementation Rules (violate any of these and auth fails)

- Compute a fresh signature and timestamp for **every** request. Do not cache either.
- The `Date` header sent and the date used in the signing input **must be byte-identical**.
- If the host running VCH is more than a few minutes off UTC, every request will be rejected. Ensure NTP is running on production VPSes.
- Use the **API Secret as the HMAC key**, not the API Key. The API Key only appears in the final `Authtoken` string as `keyId=`.
- URL-encode the base64 output before inserting into the template. Python's `urllib.parse.quote(..., safe="")` is correct. The `safe=""` argument is required — without it, `/` and `+` characters are left raw and break the signature.
- Use the GMT timestamp format exactly. Python's `email.utils.formatdate(usegmt=True)` produces this format correctly. Do NOT use `datetime.utcnow().strftime(...)` naively — weekday and month abbreviations must be English regardless of host locale.

#### Current Portal Credentials for VCH

- **API Key (from portal Access tab):**
  ```
  eyJvcmciOiI2NDM4MGYxNGFkZGJiYTAwMDE4MWYwMTEiLCJpZCI6IjNhMWM2Y2NmMmEwMTRlYmI5MGQwOTYxNmJjZDJiOWE0IiwiaCI6Im11cm11cjEyOCJ9
  ```
- **API Secret:** ✅ Obtained from portal Access tab, stored in environment. Same key/secret pair successfully authenticates against VSS.

#### Error Observed on CVD

| Attempt | Server response |
|---------|----------------|
| All variants with correct HMAC-SHA1 signed headers | `403 {"error":"Requested endpoint is forbidden"}` |

Note: The same signing method returns `200` with valid JSON from VSS. This is **not** an auth signing issue — it is a CVD-specific product/route/entitlement issue.

#### Errors Observed During Earlier Testing (before the security protocol was implemented — historical record only)

| Attempt | Server response |
|---------|----------------|
| No `Authtoken` header | `401: "Invalid Request. No security header."` |
| `Authtoken: <api_key_only>` | `400: "Authorization field missing, malformed or invalid"` |
| `Authorization: Bearer <api_key>` | `401: "No security header"` (wrong header name) |
| `api_key=<key>` as query param | `401` |

These are all resolved now that HMAC-SHA1 signing is implemented correctly.

#### Key CVD Response Fields for Image Integration

```json
{
  "result": {
    "year": "2024",
    "make": "Ford",
    "model": "F-150",
    "vehicles": [
      {
        "styleId": 403565,
        "trim": "Limited",
        "bodyType": "SuperCrew Cab Styleside"
      }
    ],
    "exteriorColors": [
      {
        "colorCode": "G1K",
        "description": "Blue Jeans Metallic",
        "rgbHexValue": "#112B3B",
        "installCause": "B"
      }
    ]
  }
}
```

`styleId` feeds the Media Server's `/style/{styleId}` lookup. `colorCode` is matched against each color-matched image's `primaryColorOptionCode` to filter the gallery down to the vehicle's actual paint.

---

## Integration Architecture

### Data Flow

```
VIN
 │
 ├─── [Path 1: CVD Available] ──→ CVD API ──→ styleId + colorCode
 │                                                │
 │                                    Media Server GET /style/{styleId}
 │                                                │
 │                                    ┌───────────┴───────────┐
 │                                    │                       │
 │                              Multi-View images      Color-Matched images
 │                              (all angles)           (filtered by colorCode)
 │
 └─── [Path 2: CVD Unavailable] ──→ Year/Make/Model/Trim (from MarketCheck or DB)
                                          │
                              Media Server GET /{Country}/{Year}/{Division}/{Model}/{BodyType}
                                          │
                                    Multi-View images only
                                    (no color matching without styleId)
```

### Where This Fits in VCH's Image Pipeline

ChromeData images serve as **Tier 0 / fallback stock imagery** — clean, professional, manufacturer-quality photos. They slot into the existing pipeline like this:

1. **ChromeData stock images** — Always available for any vehicle 2010+. Used when no other images exist, or as supplementary gallery images alongside MarketCheck photos.
2. **Tier 1 (CSS frame)** — Applied to all displayed images including ChromeData.
3. **Tier 2 (Hero AI background swap)** — Can use a ChromeData exterior shot as the source for segmentation instead of a MarketCheck photo.
4. **Tier 3+ (engagement/inspection)** — Unchanged. Real vehicle photos from MarketCheck or auction take priority when available.

**Priority logic for browsing-stage display:**
1. MarketCheck real photos of the actual vehicle (if available and adequate quality)
2. ChromeData color-matched image matching the vehicle's exact paint code (via CVD path)
3. ChromeData multi-view stock image for the trim (via Media Server path)
4. "No Photo" fallback

---

## Environment Variables to Add

```env
# ChromeData Media Server (Image Gallery) — Basic HTTP Auth — WORKING
CHROMEDATA_MEDIA_USER=<account_number_from_welcome_email>
CHROMEDATA_MEDIA_PASS=<account_secret_from_welcome_email>
CHROMEDATA_MEDIA_BASE_URL=https://media.chromedata.com/MediaGallery/service

# ChromeData VSS (Vehicle Specification Service) — Tyk HMAC-SHA1 — WORKING
# Same key/secret as CVD; proves the signing implementation is correct
CHROMEDATA_VSS_BASE_URL=https://vss-api.jdpower.com/VSS/v1.0

# ChromeData CVD (VIN Descriptions) — Tyk HMAC-SHA1 — BLOCKED (403, vendor-side)
CHROMEDATA_CVD_API_KEY=eyJvcmciOiI2NDM4MGYxNGFkZGJiYTAwMDE4MWYwMTEiLCJpZCI6IjNhMWM2Y2NmMmEwMTRlYmI5MGQwOTYxNmJjZDJiOWE0IiwiaCI6Im11cm11cjEyOCJ9
CHROMEDATA_CVD_API_SECRET=<stored in AWS Secrets Manager>
CHROMEDATA_CVD_BASE_URL=https://cvd-api.jdpower.com/CVD/v1.0
# CHROMEDATA_CVD_PROFILE_KEY=<unknown — may be required per support response>

# Shared Tyk signing credentials (used by both VSS and CVD)
# CVD_API_KEY above and the secret are the same pair that works for VSS

# Feature flags
CHROMEDATA_MEDIA_ENABLED=true
CHROMEDATA_VSS_ENABLED=true         # VSS authenticates cleanly; safe to enable
CHROMEDATA_CVD_ENABLED=false        # keep disabled until ChromeData Support resolves 403
```

Both secrets belong in AWS Secrets Manager per the VCH PRD (section 16.3), not in plaintext `.env` in production.

---

## Implementation Steps

### Step 1: Create `backend/app/integrations/chromedata_client.py`

Build a client class with three methods, following the existing `ExternalServiceClient` base class pattern (retry policy, circuit breaker, stub mode) used by `docusign_client.py`.

**`get_media_by_style_id(style_id: int) -> dict`**
- Calls `GET {MEDIA_BASE_URL}/style/{style_id}.json`
- Uses Basic HTTP auth with `CHROMEDATA_MEDIA_USER` / `CHROMEDATA_MEDIA_PASS`
- Returns parsed JSON with `view` (multi-view) and `colorized` (color-matched) image arrays
- Each image object should be normalized to: `{ url, shotCode, width, height, background, colorCode?, rgbHex? }`

**`get_media_by_ymmt(year, division, model, body_type=None) -> dict`**
- Calls `GET {MEDIA_BASE_URL}/US/{year}/{division}/{model}.json` (or `.../{model}/{bodyType}.json` if body_type provided)
- URL-encode each path segment — model names like "Silverado 1500" contain spaces
- Same basic auth as above
- Fallback when no styleId is available

**`decode_vin(vin: str) -> dict`** (CVD — gated behind `CHROMEDATA_CVD_ENABLED`)
- Calls `GET {CVD_BASE_URL}/vin/{vin}`
- Builds fresh `Authtoken` + `Date` headers on every call using the HMAC-SHA1 reference implementation above (extract `build_cvd_auth_headers` into a private helper `_build_auth_headers()`)
- Returns `styleId`, `exteriorColors` (with `colorCode`), `year`, `make`, `model`, `trim`, `bodyType`
- Unit-test `_build_auth_headers()` against the verified sample from the PDF (expected signature: `nY9NLuyne8IGbo4KHTcIj9DRpi8%3D`) before touching live credentials
- On `401` or `440` responses, log the response body at WARN (the Tyk gateway returns helpful error messages) but **never** log the secret or the Authtoken value

### Step 2: Create `backend/app/services/chromedata_service.py`

Service layer that orchestrates the two APIs:

**`resolve_chromedata_images(vin: str, year: int, make: str, model: str, trim: str | None) -> list[dict]`**

Logic:
1. If CVD enabled → call `decode_vin(vin)` → get `styleId` and `colorCode`
2. If styleId obtained → call `get_media_by_style_id(styleId)`
3. Filter color-matched images to match the vehicle's actual `colorCode`
4. If CVD unavailable or failed → fall back to `get_media_by_ymmt(year, make, model)`
5. Return normalized list of image objects sorted by display priority:
   - Exterior front ¾ (shot 01) first
   - Exterior rear ¾ (shot 02) second
   - Exterior profile (shot 03) third
   - Interior full dash (shot 12) fourth
   - Remaining interior shots by code ascending
6. Prefer Large (1280) or XL (2100) size, white background (JPG)
7. Cache results by styleId (or by YMMT hash) with a 7-day TTL. The CVD signature must not be cached — it's per-request — but the CVD response body and the Media Server response body can be.

### Step 3: Wire Into Existing Image Pipeline

In `backend/app/services/image_pipeline_service.py`, modify `resolve_vehicle_display_context()`:

- After checking for Tier 2/3 assets and before falling back to `vehicle.images`, insert a ChromeData resolution step
- If no MarketCheck images or hero image exists, call `resolve_chromedata_images()`
- Store returned URLs as `SOURCE_CACHE` tier assets in the `vehicle_image_assets` table with `source_type = "chromedata"`
- These become the fallback gallery for vehicles without real photos

### Step 4: Frontend — No Changes Required

The existing `InventoryExplorer.tsx` and `VehicleDetailPanel.tsx` components already render whatever image URLs come from the backend's display context. ChromeData URLs (`media.chromedata.com/...`) will render like any other image URL. The Tier 1 CSS frame applies automatically.

### Step 5: Operational Safeguards (CVD-specific)

- **NTP must be running** on any host that calls CVD or VSS. Clock drift of more than a few minutes invalidates the signature.
- Add a **liveness check** that calls VSS (known-working) once per hour. Alert if VSS fails — that would indicate a signing regression or credential rotation. Do NOT gate CVD-specific alerts on VSS health; they test different entitlements.
- On 401/440 failures, **circuit-break** to the YMMT fallback path automatically rather than surfacing errors to users. The YMMT path still produces usable stock images without VIN-exact color matching.
- **Handle 403 distinctly from 401/440.** A 403 on CVD means entitlement/route issue, not a transient auth problem — do not retry; log once and escalate.

### Step 6: VSS as a Potential CVD Substitute (Exploratory)

VSS (`https://vss-api.jdpower.com/VSS/v1.0`) is authenticating successfully with the same signing flow. Before waiting indefinitely for CVD, check whether VSS can serve the same purpose:

1. Pull the VSS OpenAPI spec from the portal's Technical Docs tab.
2. Check whether VSS has a VIN-decode endpoint that returns Chrome `styleId` and exterior color codes.
3. If yes → build the VIN → styleId → Media Server pipeline on VSS and treat CVD as a future optimization.
4. If no → wait for ChromeData Support response on CVD.

---

## Testing Checklist

### Algorithm verification (COMPLETE)

1. ✅ **Signature unit test** — Python reference implementation matches the PDF's sample signature (`nY9NLuyne8IGbo4KHTcIj9DRpi8%3D`).
2. ✅ **VSS live test** — `GET https://vss-api.jdpower.com/VSS/v1.0/years` with HMAC-SHA1 signed headers returns `200` with valid data. This confirms signing works end-to-end in production.

### Media Server path (can ship today)

3. **Media Server basic auth** — Confirm `GET https://media.chromedata.com/MediaGallery/service/style/403565.json` with basic auth returns image URLs.
4. **YMMT fallback** — Confirm `GET .../service/US/2025/Chevrolet/Silverado%201500.json` returns stock images.
5. **Image URL rendering** — Confirm returned URLs load actual JPG/PNG images in a browser.

### CVD path (blocked — vendor response required)

6. ⚠️ **CVD single VIN decode** — Currently returns `403 {"error":"Requested endpoint is forbidden"}` on all path variants. Re-run only after ChromeData Support confirms entitlement/path/profileKey.

### General

7. **Cache behavior** — Confirm repeated lookups for the same styleId hit cache, not the API.
8. **Shot code ordering** — Confirm exterior front ¾ is always the primary/first image.
9. **403 handling** — Confirm CVD 403 responses do NOT trigger retries and do fall through cleanly to the YMMT fallback.

---

## Current Status

**Auth implementation is complete and proven correct.** The HMAC-SHA1 signing flow works against VSS in production. The remaining blocker is **not code** — it's a CVD-specific vendor issue (entitlement, profile, or endpoint path).

| Component | Status | Next action |
|-----------|--------|------------|
| Media Server | ✅ Working | Ship now with YMMT fallback |
| VSS | ✅ Working | Optional — can use for VIN→styleId as a substitute for CVD if vendor confirms VSS returns styleId |
| CVD | ⚠️ 403 from vendor | Wait for ChromeData Support response to the open ticket |

**While waiting for ChromeData Support:**

1. **Ship Media Server + YMMT today.** Stock exterior and interior images start serving immediately using Year/Make/Model lookups from data already in the VCH vehicle database. No CVD dependency.
2. **Investigate VSS as a possible CVD substitute.** If VSS returns enough data to resolve a VIN to a Chrome `styleId` and paint code, the pipeline could use VSS instead of CVD and achieve the same end result. Check the VSS OpenAPI spec in the portal.
3. **Keep the CVD client code built but flag-gated.** When support clarifies the entitlement / profile / path question, flipping `CHROMEDATA_CVD_ENABLED=true` (and possibly adding a `profileKey` parameter) should be the only required change.

**Questions sent to ChromeData Support (awaiting response):**

1. Does CVD require a separate product entitlement from VSS, even when using the same portal key/secret pair?
2. Does CVD require a different key/secret pair than VSS?
3. Is there a required `profileKey` for CVD production calls, and if so, where can we obtain the active value?
4. What is the exact current production CVD endpoint path for VIN decode — `GET /vin/{vin}`, `GET /vindescription/{locale}/{vin}`, `GET /vindescription` with query params, or something else?
5. Can they send one known-good production sample request for CVD (method, path, headers, profileKey usage)?

**The Media Server path can ship today.** Do not block on CVD. The color-exact matching feature is an enhancement, not a prerequisite for displaying manufacturer-quality stock images on the site.