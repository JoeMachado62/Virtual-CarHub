# ChromeData Integration — Technical Reference

**Prepared for:** ChromeData / J.D. Power Technical Support
**Application:** VirtualCarHub (VCH) — Wholesale Vehicle Marketplace
**Date:** April 2026
**Contact:** info@virtualcarhub.com

---

## 1. Overview

VirtualCarHub integrates three ChromeData API products to display professional factory reference images for wholesale vehicle listings:

| Service | Purpose | Auth | Base URL |
|---------|---------|------|----------|
| **CVD** (VIN Descriptions) | Decode VIN → `styleId` + exterior colors | HMAC-SHA1 (Tyk) | `https://cvd-api.jdpower.com/CVD/v1.0` |
| **VSS** (Vehicle Selector) | Year/Make/Model → `styleId` (fallback) | HMAC-SHA1 (Tyk) | `https://vss-api.jdpower.com/VSS/v1.0` |
| **Media Server** (Image Gallery) | `styleId` → color-matched vehicle images | Basic Auth | `https://media.chromedata.com/MediaGallery/service` |

**Data flow:**
```
VIN
 │
 ├─→ CVD /vin/{vin} → styleId + exteriorColors (colorCode, rgbHex)
 │         │
 │         └─→ Media Server /style/{styleId} → colorized + view images
 │                    │
 │                    ├─ Colorized images filtered by vehicle's colorCode
 │                    └─ Transparent background (PNG) preferred over white (JPG)
 │
 └─→ [Fallback if CVD unavailable]
       VSS /makes → /models → /styles → styleId
            │
            └─→ Media Server /style/{styleId} (same as above)
```

---

## 2. Authentication — HMAC-SHA1 (CVD & VSS)

Both CVD and VSS use the Tyk Shared Secret Security Protocol. A fresh signature is computed for every request.

### Signature Algorithm

```python
import hmac, hashlib, base64
from urllib.parse import quote
from email.utils import formatdate

def build_auth_headers(api_key: str, api_secret: str) -> dict:
    # 1. Generate RFC 1123 UTC date
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    # e.g. "Tue, 22 Apr 2026 17:40:21 GMT"

    # 2. Build signing input (literal "date: " prefix)
    signing_input = f"date: {date}"

    # 3. HMAC-SHA1 with api_secret as key
    mac = hmac.new(
        api_secret.encode("utf-8"),
        msg=signing_input.encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()

    # 4. Base64 encode → URL encode (safe="" to encode +/= chars)
    sig_b64 = base64.b64encode(mac).decode("ascii")
    sig_encoded = quote(sig_b64, safe="")

    # 5. Assemble Authtoken header
    authtoken = (
        f'Signature keyId="{api_key}",'
        f'algorithm="hmac-sha1",'
        f'signature="{sig_encoded}"'
    )

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
        "Date": date,
        "Authtoken": authtoken,
    }
```

### Required Headers (all four mandatory)

| Header | Value |
|--------|-------|
| `Accept` | `application/json` |
| `Content-Type` | `application/json` |
| `Date` | RFC 1123 UTC timestamp (must match signing input exactly) |
| `Authtoken` | `Signature keyId="<API_KEY>",algorithm="hmac-sha1",signature="<URL_ENCODED_SIG>"` |

---

## 3. API Endpoints Used

### 3.1 CVD — VIN Decode

**Primary endpoint (confirmed working with profileKey):**

```
GET /vin/{VIN}?profileKey=CVDStandard&vinWithAllContent=true&incRgbHex=true
    &includeAltModel=true&includeVehicleIndicator=true&language_Locale=en_US
```

**Curl example:**
```bash
# Generate auth headers dynamically (see Python above), then:
curl -X GET \
  'https://cvd-api.jdpower.com/CVD/v1.0/vin/3TYLB5JN4ST082544?profileKey=CVDStandard&vinWithAllContent=true&incRgbHex=true&includeAltModel=true&includeVehicleIndicator=true&language_Locale=en_US' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Date: Tue, 22 Apr 2026 17:40:21 GMT' \
  -H 'Authtoken: Signature keyId="<API_KEY>",algorithm="hmac-sha1",signature="<COMPUTED_SIG>"'
```

**Fields extracted from response:**
```json
{
  "result": {
    "year": "2025",
    "make": "Toyota",
    "model": "Camry",
    "vehicles": [
      {
        "styleId": 425226,
        "bodyType": "Sedan",
        "trim": "XSE"
      }
    ],
    "exteriorColors": [
      {
        "colorCode": "085",
        "description": "Wind Chill Pearl",
        "genericDesc": "White",
        "rgbHexValue": "#E2E1DE",
        "installCause": "B",
        "primary": true,
        "type": 1
      }
    ]
  }
}
```

**We use:**
- `vehicles[0].styleId` → feeds Media Server style lookup
- `exteriorColors[].colorCode` → filters color-matched images
- `exteriorColors[].installCause` → "B" (Build), "E" (Engineered), "V" (VIN pattern) indicate factory-confirmed color
- `exteriorColors[].genericDesc` → text-matched against listing's exterior color when `installCause` is empty

### 3.2 VSS — Vehicle Selector (Fallback for styleId)

Used when CVD is unavailable. Three sequential calls:

```bash
# Step 1: Get make code
curl 'https://vss-api.jdpower.com/VSS/v1.0/makes?profileKey=CVDStandard&year=2024&locale=en_US' \
  -H 'Authtoken: ...' -H 'Date: ...'
# Returns: [{"makeCode": "FO", "make": "Ford"}, ...]

# Step 2: Get model names
curl 'https://vss-api.jdpower.com/VSS/v1.0/models?profileKey=CVDStandard&year=2024&makeCode=FO&locale=en_US' \
  -H 'Authtoken: ...' -H 'Date: ...'
# Returns: [{"model": "F-150"}, {"model": "Expedition"}, ...]

# Step 3: Get styles (styleId)
curl 'https://vss-api.jdpower.com/VSS/v1.0/styles?profileKey=CVDStandard&year=2024&makeCode=FO&model=F-150&locale=en_US' \
  -H 'Authtoken: ...' -H 'Date: ...'
# Returns: [{"styleId": 443516, "trimName": "XLT", "bodyType": "SuperCrew"}, ...]
```

**Caching:** Make codes and model names are cached in-memory per process lifetime to reduce repeat calls.

### 3.3 Media Server — Image Gallery

**Auth:** Basic HTTP Auth (not HMAC). Different credentials from CVD/VSS.

**Style-based lookup (preferred — uses styleId from CVD or VSS):**
```bash
curl 'https://media.chromedata.com/MediaGallery/service/style/425226.json' \
  -H 'Authorization: Basic <base64(username:password)>'
```

**YMMT-based crawl (fallback when no styleId):**
```bash
# Navigate: Country → Year → Division → Model → BodyType
curl 'https://media.chromedata.com/MediaGallery/service/US/2024/Ford/F-150/SuperCrew.json' \
  -H 'Authorization: Basic <base64(username:password)>'
```

**Response structure:**
```json
{
  "view": [
    {
      "@shotCode": "01",
      "@width": "1280",
      "@height": "960",
      "@backgroundDescription": "Transparent",
      "@href": "https://media.chromedata.com/MediaGallery/media/..."
    }
  ],
  "colorized": [
    {
      "@primaryColorOptionCode": "085",
      "@primaryRGBHexCode": "E2E1DE",
      "@shotCode": "01",
      "@width": "1280",
      "@height": "960",
      "@backgroundDescription": "Transparent",
      "@href": "https://media.chromedata.com/MediaGallery/media/..."
    }
  ]
}
```

---

## 4. Image Selection Logic

### 4.1 Color Matching Priority

1. **VIN-confirmed color** (`installCause` = B/E/V/I from CVD) → use that `colorCode`
2. **Text-matched color** — match listing's `exterior_color` text (e.g. "Black") against CVD `genericDesc` fields → find the matching `colorCode`
3. **Stored paint code** — use the vehicle's existing `paint_code` from auction/dealer data
4. **No color match** — fall back to generic `view` images (non-colorized)

### 4.2 Image Selection from Media Response

**Colorized images** (color-matched exterior, 3 angles):
- Filtered by matching `@primaryColorOptionCode` to the selected `colorCode`
- Transparent background (`@backgroundDescription=Transparent`) preferred over white
- Shot codes used: 01 (front 3/4), 02 (rear 3/4), 03 (side profile)

**View images** (generic, used as fallback):
- Only 3 basic exterior angles (01, 02, 03) — no expanded angles to avoid showing wrong colors
- Transparent background preferred

**Interior detail images** (expanded set for vehicle detail page):
- Shot codes: 11 (driver dash), 12 (full dashboard), 13 (door open), 18 (stereo), 24 (trunk), 25 (engine), 28 (rear seats), 43 (center console), 44 (passenger dash), 46 (navigation)
- Exterior angles excluded from detail set to avoid color mismatch

### 4.3 Resolution/Size Tiers

| Context | Preferred Size | Fallback |
|---------|---------------|----------|
| Search card thumbnail | 640x480 | 1280x960 |
| Vehicle detail page | 1280x960 | 2100x1575 |

### 4.4 Background Preference

All contexts prefer `Transparent` (PNG) over `White` (JPG) backgrounds.

---

## 5. API Call Volume Per Search

| Scenario | Calls per Vehicle | 18-Vehicle Page |
|----------|-------------------|-----------------|
| **Cached** (style_id stored) | 0 | 0 |
| **CVD success** | 2 (CVD + Media) | 36 |
| **CVD 403, VSS fallback** | 5 (CVD + 3 VSS + Media) | 90 |
| **All HMAC fail, YMMT crawl** | 5 (CVD + 4 Media crawl) | 90 |
| **Worst case (cold, all fail)** | 9 | 162 |

**Retry policy:** Single attempt, no retry (max_retries=1). Circuit breaker opens after 5 failures, recovers after 5 minutes.

**Caching that reduces calls:**
- `features_normalized.chromedata_style_id` → skips all CVD/VSS calls on repeat lookups
- `VehicleImageAsset` records with `source_kind="chromedata"` → skips entire ChromeData flow if images already cached
- In-memory VSS make/model caches → `/makes` and `/models` called once per year+make combo per process

---

## 6. Error Handling

| HTTP Status | Meaning | VCH Behavior |
|-------------|---------|--------------|
| 200 | Success | Process response normally |
| 403 | Quota exceeded or entitlement issue | Skip VSS (same credentials), fall to YMMT Media crawl |
| 404 | VIN/style/model not found | Does NOT trip circuit breaker; falls to next lookup method |
| 401/440 | Auth failure | Logs warning, circuit breaker counts failure |
| 5xx | Server error | Circuit breaker counts failure; opens after 5 failures |

---

## 7. Questions for ChromeData Support

1. **Quota:** Our current 5,000-call test quota is consumed in approximately 30-50 search sessions. For production with ~500 vehicles and ~50 daily users, we estimate needing **25,000-50,000 calls/month** across CVD + VSS. What tier provides this?

2. **CVD batch endpoint:** Does CVD support a batch VIN decode endpoint (multiple VINs in one call)? This would reduce our per-search call count from ~36 to ~2.

3. **Media Server caching headers:** Does the Media Server response include `Cache-Control` or `ETag` headers? We could implement HTTP-level caching to avoid refetching images we've already retrieved.

4. **CVD/VSS unified quota:** Are CVD and VSS calls counted against the same quota pool? If CVD 403s, will VSS also 403?

5. **Color confirmation:** For VINs where `installCause` is empty on all `exteriorColors`, is there a way to get the factory-installed color? Currently we fall back to text-matching the listing's color description against `genericDesc`.
