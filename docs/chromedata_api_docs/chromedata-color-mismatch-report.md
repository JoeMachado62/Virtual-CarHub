# ChromeData Color Resolution Failure Report

**Date:** 2026-05-10
**Prepared by:** Virtual CarHub Engineering
**Purpose:** Trace a color mismatch for ChromeData Tech Support investigation

---

## 1. Problem Summary

A **2024 Mazda CX-90 3.3 Turbo Premium Package** (VIN `JM3KKDHD4R1162844`) with a **Gold** exterior color is displaying **red** stock images from ChromeData's Media Gallery. The color resolution pipeline failed to match the listing's "Gold" exterior color to any CVD-returned color, resulting in uncolored fallback images being served.

---

## 2. Vehicle Details

| Field | Value |
|-------|-------|
| **VIN** | `JM3KKDHD4R1162844` |
| **Year** | 2024 |
| **Make** | Mazda |
| **Model** | CX-90 |
| **Trim** | 3.3 Turbo Premium Package |
| **Listing Exterior Color** | Gold |
| **Source Platform** | OVE (Manheim) |

---

## 3. API Call Trace

### Step 1: CVD VIN Decode

**Request:**
```
GET {cvd_base_url}/vin/JM3KKDHD4R1162844
    ?vinWithAllContent=true
    &incRgbHex=true
    &includeAltModel=true
    &includeVehicleIndicator=true
    &language_Locale=en_US
    &profileKey={profileKey}
```

**Authentication:** HMAC-SHA1 via Tyk Shared Secret Security Protocol
```
Headers:
  Accept: application/json
  Content-Type: application/json
  Date: {RFC 7231 formatted date}
  Authtoken: Signature keyId="{api_key}",algorithm="hmac-sha1",signature="{HMAC-SHA1(api_secret, 'date: {Date}')}"
```

**Result:** SUCCESS - Decoded to **styleId 437231** (3.3 Turbo Premium AWD)

**Exterior Colors Returned (8 total):**

| # | colorCode | description | genericDesc | installCause | rgbHexValue |
|---|-----------|-------------|-------------|--------------|-------------|
| 0 | `47S` | Platinum Quartz | **Tan** | **B** (Build/Factory) | `#B5B1AB` |
| 1 | `41W` | Jet Black Mica | Black | _(none)_ | `#111214` |
| 2 | `42M` | Deep Crystal Blue Mica | Blue | _(none)_ | `#252A3B` |
| 3 | `51K` | Rhodium White Premium | White | _(none)_ | `#E3E3E3` |
| 4 | `46G` | Machine Gray Metallic | Gray | _(none)_ | `#38363B` |
| 5 | `46V` | Soul Red Crystal Metallic | **Red** | _(none)_ | `#90001E` |
| 6 | `45P` | Sonic Silver | Silver | _(none)_ | `#B6B9BE` |
| 7 | `51F` | Artisan Red Premium | **Red** | _(none)_ | `#36070E` |

**Key Observation:** The VIN decoded with `installCause=B` (factory-installed) for color code `47S` — **Platinum Quartz** with `genericDesc=Tan`. No color in the response has `genericDesc=Gold` or any description containing the word "Gold".

---

### Step 2: Color Resolution (Our Code)

Our pipeline attempts to match the listing's exterior color text ("Gold") against the CVD exterior colors:

**Algorithm:**
1. Filter candidates to style 437231
2. Filter to "exact" colors (`installCause` in {B, E, V, I}) -- yields only `47S` (Platinum Quartz / Tan)
3. Text-match "Gold" against each candidate's `genericDesc` and `description` fields
4. Normalize via canonical color tokens: `gold` is a recognized color word in our dictionary

**Match Attempts:**
- `"gold"` vs `"tan"` (47S genericDesc) -- NO MATCH
- `"gold"` vs `"platinum quartz"` (47S description) -- NO MATCH
- `"gold"` vs `"black"` (41W genericDesc) -- NO MATCH
- `"gold"` vs `"blue"` (42M genericDesc) -- NO MATCH
- `"gold"` vs `"white"` (51K genericDesc) -- NO MATCH
- `"gold"` vs `"gray"` (46G genericDesc) -- NO MATCH
- `"gold"` vs `"red"` (46V genericDesc) -- NO MATCH
- `"gold"` vs `"silver"` (45P genericDesc) -- NO MATCH
- `"gold"` vs `"red"` (51F genericDesc) -- NO MATCH

**Result:** No text match found. Since "Gold" IS a recognized color word, our pipeline returns `color_info = None` (intentional -- we'd rather serve no color than guess wrong).

**Root Cause:** The actual factory color for this VIN is **Platinum Quartz** (code `47S`), which ChromeData categorizes under `genericDesc=Tan`. The OVE listing describes this color as **"Gold"**. Our text matcher cannot bridge "Gold" to "Tan" or "Platinum Quartz" because:
- "Gold" and "Tan" are different color tokens
- "Gold" does not appear anywhere in "Platinum Quartz"
- We have no alias mapping from "Gold" to "Tan" (our alias table maps grey->gray, charcoal->gray, pearl->white, etc., but has no gold->tan mapping)

---

### Step 3: Media Gallery Request

**Request:**
```
GET {media_base_url}/style/437231.json
```

**Authentication:** HTTP Basic Auth (separate credentials from CVD)

**Response:** The Media Gallery returned **0 colorized images** and **0 generic/stock images** in the standard `colorized`/`genericImages` containers. Instead, all images were returned in the `view` container (uncolored reference shots).

**Images returned:** All are in the `view` array -- these are angle-specific renders without color association:

| shotCode | widths available | backgroundDescription |
|----------|------------------|-----------------------|
| 01 | 320, 640, 1280, 2100 | Transparent, White |
| 02 | 320, 640, 1280, 2100 | Transparent, White |
| 03 | 320, 640, 1280, 2100 | Transparent, White |
| 11-47 | 320, 640, 1280, 2100 | Transparent (interior) |

**Key Observation:** Since `color_info` was `None` from Step 2, our code passed `selected_color_code=None` to the media parser. With no color code, the colorized filter was skipped (`matched_colorized = []`), and the pipeline fell back to the `view` container images.

**The `view` images appear to be rendered in a single default color (red/Soul Red Crystal Metallic) since no colorCode parameter is embedded in the view URLs.** This is the source of the wrong-color images.

---

## 4. Stored Asset Metadata (Database)

All 14 ChromeData image assets stored for this VIN show the failure:

| Field | Value |
|-------|-------|
| `color_code` | _(empty)_ |
| `color_description` | _(empty)_ |
| `color_generic` | _(empty)_ |
| `color_match_exact` | `false` |
| `color_match_source` | _(empty)_ |
| `match_level` | `vin` |
| `style_id` | `437231` |
| `style_description` | `3.3 Turbo Premium AWD` |
| `color_pipeline_version` | `2` |

---

## 5. Questions for ChromeData Tech Support

### 5a. CVD Color Classification

The VIN `JM3KKDHD4R1162844` was factory-built with color code `47S` (Platinum Quartz), classified as `genericDesc=Tan`. The OVE auction listing describes this color as **"Gold"**.

- **Is "Tan" the intended generic classification for Platinum Quartz (47S)?** The RGB hex `#B5B1AB` appears to be a warm beige/sand tone that could reasonably be described as "Gold" by dealers.
- **Does ChromeData have a "Gold" genericDesc category?** If so, would Platinum Quartz qualify for reclassification?
- **Is there a supplementary color taxonomy** (beyond genericDesc) that includes broader color family mappings we could use for fuzzy matching?

### 5b. Media Gallery — No Colorized Images for Style 437231

Our Media Gallery query for `GET /style/437231.json` returned **zero colorized images** -- all images were in the `view` container with no color association.

- **Is this expected for style 437231?** Are colorized images not yet available for the 2024 Mazda CX-90?
- **If colorized images exist**, is there a different endpoint or parameter we should be using to access them?
- **What color are the `view` container images rendered in?** They appear to be red (Soul Red Crystal Metallic) -- is this the default render color for this style?

### 5c. Best Practice for Color Fallback

When CVD returns colors but our listing color text doesn't match any `genericDesc`:
- **Is there a recommended API for color family mapping** (e.g., "Gold" -> closest available color)?
- **Can we request `view` images filtered by colorCode?** For example, append `?colorCode=47S` to get Platinum Quartz renders from the view container?

---

## 6. Our Color Resolution Code (Reference)

### Color Matching Function

```python
def _match_color_by_text(colors, exterior_text):
    """Match free-text exterior color against CVD genericDesc/description."""
    target = normalize(exterior_text)       # "gold"
    target_tokens = set(target.split())     # {"gold"}
    target_color_tokens = canonical(target_tokens)  # {"gold"}

    for item in colors:
        code = item["colorCode"]
        for field in ("genericDesc", "description"):
            desc = normalize(item[field])
            desc_tokens = set(desc.split())
            desc_color_tokens = canonical(desc_tokens)

            if target == desc:
                return code  # Exact match

            if target_color_tokens & desc_color_tokens:
                score = 80 + overlap_count  # Color token intersection

            if target_tokens.issubset(desc_tokens):
                score = 60 + token_count    # Substring match

    return best_code or None
```

### Color Word Dictionary

```python
COLOR_WORDS = {
    "black", "blue", "brown", "gold", "gray", "grey", "green", "orange",
    "purple", "red", "silver", "tan", "white", "yellow", "beige", "bronze",
    "copper", "charcoal", "maroon", "pearl", "metallic",
}

COLOR_ALIASES = {
    "grey": "gray",
    "charcoal": "gray",
    "pearl": "white",
    "beige": "tan",
    "bronze": "brown",
    "copper": "brown",
    "maroon": "red",
    # NOTE: No "gold" alias exists — this is part of the problem
}
```

### Failure Decision Point

```python
def _select_listing_aware_color(colors, style_id, preferred_code, exterior_color_text):
    candidates = style_body_color_candidates(colors, style_id)
    installed = [c for c in candidates if is_exact_color(c)]  # installCause in {B,E,V,I}

    if exterior_color_text:                    # "Gold"
        text_match = match_by_text(installed, "Gold")  # -> None (no "gold" in any genericDesc)
        text_match = match_by_text(candidates, "Gold") # -> None (same result across all 8 colors)

        if has_color_token("Gold"):            # True -- "gold" is in COLOR_WORDS
            return None                        # <-- INTENTIONAL BAILOUT: recognized color, no match
            # This prevents guessing wrong, but means NO color is selected

    # ... fallback logic never reached because of the bailout above
```

---

## 7. Possible Fixes (Internal)

Regardless of ChromeData's response, we are considering these internal improvements:

1. **Add `"gold": "tan"` to our COLOR_ALIASES map** -- This would let "Gold" listings match "Tan" genericDesc colors like Platinum Quartz.

2. **Use the CVD `installCause=B` color as a confident fallback** -- When CVD returns a factory-installed color for the VIN but our text matching fails, the factory color IS the correct color. In this case, `47S` (Platinum Quartz) has `installCause=B`, meaning ChromeData confirmed this is the color the vehicle was built with. We should trust this over the listing's free-text "Gold" label.

3. **Request colorized Media images using the installCause=B colorCode** -- Even when text matching fails, if we have a factory-confirmed color code, we should use it to filter colorized images from the Media Gallery.

---

## 8. Image URLs Currently Displayed (Wrong Color)

These are the red-tinted `view` fallback images currently being served:

**Hero (shot 01):**
```
https://media.chromedata.com/MediaGallery/media/.../2024MAS110112_1280_01.png
https://media.chromedata.com/MediaGallery/media/.../2024MAS110112_640_01.png
```

**Gallery (shots 02, 03):**
```
https://media.chromedata.com/MediaGallery/media/.../2024MAS110113_1280_02.png
https://media.chromedata.com/MediaGallery/media/.../2024MAS110113_640_02.png
https://media.chromedata.com/MediaGallery/media/.../2024MAS110114_640_03.png
https://media.chromedata.com/MediaGallery/media/.../2024MAS110114_1280_03.png
```

**Detail/Interior (shots 11-46):**
```
2024MAS110118_1280_11.png
2024MAS110119_1280_12.png
2024MAS110120_1280_13.png
2024MAS110121_1280_18.png
2024MAS110124_1280_28.png
2024MAS110125_1280_43.png
2024MAS110126_1280_44.png
2024MAS110127_1280_46.png
```

**Expected:** Images in Platinum Quartz / Gold (color code `47S`, RGB `#B5B1AB`)
**Actual:** Images appear to be rendered in Soul Red Crystal Metallic or similar red

---

_End of report._
