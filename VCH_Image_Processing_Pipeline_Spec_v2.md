# VirtualCarHub — Image Processing & Display Pipeline Specification v2

## Document Purpose

This document defines the complete image handling strategy for VirtualCarHub.com's inventory display system. It covers how vehicle images are sourced, processed, branded, stored, and displayed across the full vehicle lifecycle — from initial browsing through purchase and delivery. Any agent building or modifying the inventory display pipeline should treat this as the authoritative reference for image-related logic.

---

## 1. Business Context

VirtualCarHub is an AI-first virtual dealership that sources vehicles at wholesale cost and sells direct to consumers. The business model has a critical characteristic that shapes the entire image pipeline:

**Every vehicle VirtualCarHub sells is purchased through a wholesale auction platform, regardless of how it was initially discovered.**

This is non-negotiable. Even when a vehicle is first presented to the consumer as a dealer inventory listing, VirtualCarHub will negotiate with that dealer to wholesale the vehicle through one of the supported auction platforms. The purpose is twofold:

1. **Protection:** Auction platforms provide buyer protection programs (arbitration, return policies, condition guarantees) that protect both VirtualCarHub and the end consumer.
2. **Verification:** Auction platforms generate professional condition reports with inspection images, providing an independent third-party assessment of every vehicle.

**Marketing position:** *"Every vehicle we offer includes an independent third-party inspection by professional auction inspectors."*

### 1.1 Supported Auction Platforms

VirtualCarHub sources vehicles through three wholesale auction platforms, each with its own buyer protection program:

| Platform | Buyer Protection Program | Condition Report | Notes |
|---|---|---|---|
| **Manheim** | DealShield | Manheim Condition Report (CR) | Largest wholesale auction. Dealer-lot vehicles enter via **Manheim Express**. |
| **OpenLane** (formerly Adesa + Backlot Cars) | OpenLane Arbitration / Return Policy | OpenLane Condition Report | Now owned by Carvana. Combined Adesa and Backlot Cars platforms. |
| **Ally Smart Auction** | Ally Smart Auction Return Protection | Ally Condition Report | Ally Financial's auction platform. |

**Each platform has its own:**
- Condition report format and data structure
- Inspection image standards and angles
- Disclosure methodology for imperfections
- Buyer protection terms and arbitration process

The image pipeline must handle all three platforms' images and condition reports, normalizing them into a consistent VirtualCarHub customer experience while preserving platform-specific details for arbitration purposes.

### 1.2 Vehicle Lifecycle Stages

Every vehicle on VirtualCarHub passes through distinct stages. The image strategy changes at each:

| Stage | What the Customer Sees | Image Source | Purpose |
|---|---|---|---|
| **Browsing** | Vehicle listings on the public site | MarketCheck API images (dealer or historical) | Marketing — attract interest |
| **Engagement** | Enhanced vehicle detail page | Processed MarketCheck images (Tier 3) | Conversion — deepen interest |
| **Deal in Progress** | "My Garage" customer portal | Auction inspection images + condition report | Verification — show actual condition |
| **Post-Purchase** | Delivery tracking and records | Auction images as permanent record | Evidence — dispute resolution |

**The critical transition:** When a vehicle moves from Engagement to Deal in Progress, the image source shifts from MarketCheck marketing images to auction inspection images. This is the moment when "what the car generally looks like" is replaced by "what this specific car actually looks like right now, as verified by an independent inspector."

---

## 2. Image Source Paths

### Path A — MarketCheck Dealer Listings (Browsing-Stage Source)

These are vehicles currently listed at dealerships nationwide. Images come from the MarketCheck API and are used for the **browsing experience only**. They represent the vehicle's general appearance, not its verified current condition.

**How images are delivered:**

- MarketCheck Inventory Search API (`/v2/search/car/active`) returns a `media` object per listing.
- `media.photo_links` — Array of original image URLs from the dealer's website.
- `media.photo_links_cached` — Array of cached image URLs hosted by MarketCheck.
- Cached Image endpoint: `/v2/image/cache/car/{listing_id}/{image_id}` for reliable access.
- Use `photo_links=true` and/or `min_photo_links=5` parameters to ensure listings have adequate imagery.

**What to expect:**

- Typically 10-40 images per listing (exterior angles, interior, engine, features).
- May contain dealer overlays/watermarks in corners or along edges.
- Backgrounds will show dealer lots, showrooms, or professional photo studios.
- Quality varies — professional to phone photos.
- **These images are MARKETING ASSETS for the browsing stage, not representations of verified condition.**

---

### Path B — Auction-Discovered Vehicles (Browsing-Stage Source)

These are vehicles identified through our auction scraping system (across Manheim, OpenLane, and Ally Smart Auction). Auction images cannot be displayed directly on the public browsing site because they contain auction-specific branding and proprietary content.

**The backfill process:**

1. Auction scraper identifies a VIN at any of the three platforms.
2. System queries MarketCheck API by VIN to find the most recent dealer listing in their 14-year historical database.
3. **Assumption:** Virtually every vehicle at auction has at some point been listed on a dealer website scraped by MarketCheck.
4. System retrieves `media.photo_links_cached` and listing description/specs from the MarketCheck response.
5. These retrieved images create the VirtualCarHub browsing-stage listing.

**After backfill, Path B images enter the same browsing-stage pipeline as Path A.** The browsing experience is identical regardless of how the VIN was originally discovered.

---

### Path C — Auction Inspection Images & Condition Reports (Deal-Stage Source)

**This path applies to EVERY vehicle that progresses to a deal, regardless of whether it entered the system via Path A or Path B.**

When a vehicle transitions from browsing to deal stage:

- **Path A vehicles (dealer inventory):** VCH negotiates with the dealer to wholesale via Manheim Express, OpenLane, or Ally Smart Auction. The auction platform then inspects the vehicle, generates a condition report, and produces inspection images.
- **Path B vehicles (already at auction):** Condition report and inspection images already exist on the auction platform.

**What each auction platform provides:**

#### Manheim
- Professional inspection images from standardized angles
- Manheim Condition Report (CR) with grade scoring
- Disclosure images: close-ups of specific imperfections (scratches, dents, stains, chips, etc.)
- Each disclosure image is linked to a specific condition report line item
- DealShield protection documentation

#### OpenLane (formerly Adesa + Backlot Cars)
- Inspection images per OpenLane standards
- OpenLane Condition Report with disclosures
- Disclosure images tied to specific findings
- Arbitration/return policy documentation

#### Ally Smart Auction
- Inspection images per Ally standards
- Ally Condition Report with disclosures
- Disclosure images tied to specific findings
- Return protection documentation

**What the pipeline must handle for Path C:**

1. **Ingest** inspection images and condition report data from the specific auction platform.
2. **Normalize** the presentation — the customer should see a consistent VirtualCarHub "Inspection Report" experience regardless of which auction platform sourced the vehicle. The underlying data structure may differ, but the customer-facing display should feel unified.
3. **Preserve** all original auction images and condition report data in their unmodified form for arbitration/dispute purposes.
4. **Link** specific disclosure images to specific condition report findings so the customer can see "Scratch on rear bumper → [photo of scratch]."

**These images and the condition report become the SOURCE OF TRUTH from deal stage forward.**

---

## 3. The 4-Tier Image Processing System

All vehicle images pass through a tiered processing system. Each tier is triggered by a specific event. The VIN Deduplication Gate (Section 4) prevents redundant processing.

---

### Tier 1 — CSS Branded Frame (All Images, Always, Zero Processing Cost)

**Trigger:** Any image displayed anywhere on VirtualCarHub.com, at any lifecycle stage.

**What it does:**

- Applies a consistent VirtualCarHub branded presentation layer via CSS/frontend code — NOT image manipulation.
- Rendered entirely in the browser.

**Implementation requirements:**

- Branded border or frame using VCH brand colors (teal `#08b0c4`, orange `#ff6b11`).
- Subtle VirtualCarHub watermark or logo overlay positioned to partially obscure common dealer overlay locations (typically corners).
- Optional gradient overlay at the bottom edge for vehicle info text (year, make, model, price).
- Consistent aspect ratio enforcement via CSS `object-fit` to normalize varying image dimensions.
- All styling applied via CSS classes — the underlying image file is NEVER modified.

**Why this matters:**

- Creates instant brand consistency across ALL images regardless of source, quality, or lifecycle stage.
- Partially masks competitor dealer overlays on browsing-stage images.
- Costs nothing — no API calls, no GPU processing, no storage overhead.
- Applied universally and unconditionally.

**Important exception:** When auction inspection images are displayed in the condition report view within "My Garage," the CSS frame should be minimal — a light VCH border only. The goal in that context is transparency and clarity, not marketing. Do NOT obscure any portion of condition/disclosure images with overlays, gradients, or watermarks.

**Technical note:** This tier is implemented entirely in the frontend display layer. The backend image pipeline does not need to do anything for Tier 1. Ensure all image display components apply the appropriate VCH frame CSS class for their context (marketing frame vs. inspection frame).

---

### Tier 2 — Hero Image AI Background Swap (One Per VIN, Triggered at Ingest)

**Trigger:** A new VIN enters the VirtualCarHub database for the first time (from either Path A or Path B).

**What it does:**

- Takes the PRIMARY exterior image for the vehicle (typically the first image in `photo_links_cached` — usually a front 3/4 angle).
- Runs vehicle segmentation to isolate the car from its background.
- Places the segmented vehicle onto a standardized VirtualCarHub branded background.
- Stores the result in S3 as the "hero image" for that VIN.

**Implementation requirements:**

- Use a segmentation model (e.g., SAM2 or equivalent) to create a precise cutout of the vehicle.
- Standard VCH background template(s) — clean, professional, branded. Consider 2-3 variations to avoid visual monotony.
- Output resolution should match or exceed the source image resolution.
- Store processed hero image: `s3://vch-images/hero/{vin}/hero.webp`
- Store the source image reference for traceability.
- If segmentation confidence is below an acceptable threshold, flag for manual review rather than publishing a bad cutout.

**Where this image is used:**

- Search results grid / listing cards (the primary browsing experience).
- Social media previews and `og:image` meta tags.
- Any context where a single representative image of the vehicle is needed.

**Cost profile:**

- One image per VIN, processed once.
- At approximately 20,000-30,000 new VINs per month, this is manageable and predictable.
- Segmentation + compositing: approximately $0.03-$0.10 per image depending on model and infrastructure.

---

### Tier 3 — On-Demand Full Suite Processing (Triggered by Customer Engagement)

**Trigger:** A customer takes a meaningful engagement action on a specific vehicle:

- Favorites / saves the vehicle
- Clicks "Get More Info" or initiates an inquiry
- Starts a chat or conversation about the vehicle
- Adds to a comparison list
- Any other action indicating genuine purchase interest

**What it does:**

- Processes ALL remaining MarketCheck-sourced images for that VIN (beyond the hero image from Tier 2).
- Applies overlay/watermark detection and removal where needed.
- Optionally applies background enhancement or replacement for consistency.
- Stores all processed images in S3 for that VIN.

**Implementation requirements:**

- Classification model scans each image to detect: overlays/watermarks, competitor branding, image type (exterior, interior, engine, detail, etc.).
- For images flagged with overlays: apply inpainting/removal (e.g., LaMa model or SD inpainting).
- For exterior images: optionally apply background replacement matching the Tier 2 hero style.
- For interior images: typically leave as-is (overlays are rare on interiors, background replacement doesn't apply).
- Store processed images: `s3://vch-images/processed/{vin}/{image_index}.webp`
- Maintain a manifest file: `s3://vch-images/processed/{vin}/manifest.json` tracking processing details.

**Cost profile:**

- Only fires on vehicles with active customer interest — estimated 1-5% of total inventory.
- Average 15-25 images per vehicle needing processing.
- At approximately 500-2,000 vehicles per month reaching this trigger, volume is very manageable.

**Reminder:** These are still MARKETING IMAGES for the engagement stage. They are not representations of verified condition. The verified condition comes in Tier 4.

---

### Tier 4 — Auction Inspection & Condition Report (Triggered by Deal Milestone, ALL Vehicles)

**Trigger:** A vehicle reaches a deal milestone indicating it will be transacted through an auction platform:

- Customer has approved financing, OR
- Purchase commitment is confirmed, OR
- VCH initiates the Manheim Express / OpenLane / Ally Smart Auction transaction with the selling dealer, OR
- For vehicles already at auction: customer commits to purchase

**⚠️ THIS TIER APPLIES TO EVERY VEHICLE THAT REACHES DEAL STAGE. THERE ARE NO EXCEPTIONS.**

**What it does:**

1. Ingests the auction platform's inspection images and condition report for the specific vehicle.
2. Stores original unmodified copies of ALL auction images and condition report data.
3. Creates a normalized "VirtualCarHub Inspection Report" view for the customer portal.
4. Links disclosure images to their corresponding condition report findings.
5. Transitions the vehicle's image display from marketing images (Tiers 1-3) to verified inspection images.

**Implementation requirements by component:**

#### 4A. Auction Image Ingestion

- Scrape or API-retrieve all inspection images from the auction platform (Manheim, OpenLane, or Ally Smart Auction).
- Store originals IMMEDIATELY in their unmodified form.
- Storage key: `s3://vch-images/auction-originals/{vin}/{platform}/{timestamp}/{image_filename}`
- Where `{platform}` is one of: `manheim`, `openlane`, `ally-smart-auction`
- Compute SHA-256 hash of each image at ingest time.

#### 4B. Condition Report Ingestion

- Ingest the full condition report from the auction platform.
- Store the raw condition report data: `s3://vch-images/auction-originals/{vin}/{platform}/{timestamp}/condition_report_raw.json`
- Parse into a normalized VCH condition report schema (see Section 6).
- Store normalized version: `s3://vch-images/auction-originals/{vin}/{platform}/{timestamp}/condition_report_normalized.json`

#### 4C. Image-to-Finding Linkage

- Map specific disclosure/damage images to specific condition report line items.
- Example: Condition report states "Minor scratch, rear bumper, driver side, 3 inches" → linked to `disclosure_007.jpg` showing that scratch.
- Store mapping in the normalized condition report JSON.

#### 4D. Evidentiary Integrity (CRITICAL)

The auction original images and condition report serve as legal/business evidence of vehicle condition at time of inspection. Imperfections commonly disclosed include:

- Scratches, chips, or paint imperfections
- Interior stains, wear marks, or minor damage
- Tire wear
- Windshield chips or cracks
- Mechanical disclosures
- Prior repair evidence

**Rules for evidentiary originals:**

1. **NEVER modify, crop, resize, filter, enhance, compress, or alter original auction images in any way.**
2. **NEVER modify, redact, or alter original condition report data in any way.**
3. SHA-256 hash computed at ingest time for integrity verification of each image.
4. Metadata record per image: original URL, scrape timestamp, SHA-256 hash, auction platform, lot number, auction date.
5. These records must be retrievable and hash-verifiable for dispute resolution at any future date.
6. S3 bucket policy: versioning enabled, no delete permissions except for authorized compliance roles.
7. Retention policy: maintain indefinitely (or per legal counsel's guidance).

#### 4E. Customer Display in "My Garage"

When Tier 4 is active for a vehicle, the customer's "My Garage" portal displays:

- **Inspection Images:** The auction inspection photos presented with a minimal Tier 1 CSS frame (light VCH border, NO marketing overlays that could obscure image content).
- **Condition Report:** Presented as the "VirtualCarHub Vehicle Inspection Report" — a normalized, customer-friendly view regardless of which auction platform generated it. Must include:
  - Overall vehicle grade/score (normalized from platform-specific grading)
  - Panel-by-panel exterior condition summary
  - Interior condition summary
  - Mechanical condition summary
  - Tire condition with tread depth
  - Glass condition
  - **Disclosure gallery:** Each disclosed imperfection shown with its image and description, clearly labeled
- **Buyer Protection Info:** The applicable protection program details (DealShield, OpenLane Arbitration, or Ally Return Protection) with terms summary.
- **Label:** Images clearly labeled as "Independent Inspection Photos" or similar language — NOT "Current Vehicle Photos."

**Cost profile:**

- Fires on every vehicle reaching deal stage.
- No AI processing cost — images displayed as-is with minimal CSS framing.
- Primary costs: scraping/API access to auction platforms, storage (negligible), and the engineering effort to normalize condition reports across three platforms.

---

## 4. VIN Deduplication Gate

Before ANY image processing occurs (Tiers 2-4), check whether processed images already exist for the VIN.

```
NEW VIN ENTERS SYSTEM (Path A or B)
│
├─ Check: Does s3://vch-images/hero/{vin}/hero.webp exist?
│  ├─ YES → Skip Tier 2
│  └─ NO  → Execute Tier 2
│
├─ On customer engagement trigger:
│  ├─ Check: Does s3://vch-images/processed/{vin}/manifest.json exist?
│  │  ├─ YES → Skip Tier 3 (serve cached processed images)
│  │  └─ NO  → Execute Tier 3
│
├─ On deal milestone trigger (ALL vehicles):
│  ├─ Check: Do auction originals exist at
│  │         s3://vch-images/auction-originals/{vin}/{platform}/{timestamp}/?
│  │  ├─ YES (vehicle already at auction) → Execute Tier 4 display logic
│  │  └─ NO  (dealer vehicle being moved to auction via Express) →
│  │         Wait for auction inspection to complete, then ingest and execute Tier 4
│  │         Set vehicle status: "Pending Inspection"
```

**Edge case — VIN re-entry:**

- Tier 2 hero: Regenerate only if new listing has substantially newer images.
- Tier 3 processed: Invalidate and reprocess if source images have changed.
- Tier 4 auction originals: Each auction appearance gets its own `{platform}/{timestamp}` folder. NEVER overwrite previous auction records. A VIN may go through auction multiple times across different platforms.

---

## 5. S3 Storage Architecture

```
s3://vch-images/
│
├── hero/
│   └── {vin}/
│       └── hero.webp                              ← Tier 2 output
│
├── processed/
│   └── {vin}/
│       ├── manifest.json                          ← Tier 3 processing record
│       ├── 001_exterior_front.webp                ← Tier 3 outputs
│       ├── 002_exterior_rear.webp
│       ├── 003_interior_dash.webp
│       └── ...
│
├── auction-originals/                             ← IMMUTABLE EVIDENTIARY STORE
│   └── {vin}/
│       └── {platform}/                            ← manheim | openlane | ally-smart-auction
│           └── {scrape_timestamp}/
│               ├── metadata.json                  ← Source URL, SHA-256 hashes, lot #,
│               │                                     auction date, platform details
│               ├── condition_report_raw.json       ← Original CR data from platform
│               ├── condition_report_normalized.json← Normalized to VCH schema
│               ├── inspection_001.jpg             ← UNMODIFIED inspection images
│               ├── inspection_002.jpg
│               ├── disclosure_001.jpg             ← UNMODIFIED disclosure/damage images
│               ├── disclosure_002.jpg
│               └── ...
│
└── source-cache/
    └── {vin}/
        └── marketcheck/                           ← Cached MC images at ingest time
            ├── source_manifest.json               ← MC listing_id, URLs, retrieval date
            ├── 001.jpg
            └── ...
```

**Bucket policies:**

| Path | Versioning | Delete Access | Retention |
|---|---|---|---|
| `hero/` | Optional | Pipeline service role | Until VIN re-processed |
| `processed/` | Optional | Pipeline service role | Until VIN re-processed |
| `auction-originals/` | **REQUIRED** | **Compliance role ONLY** | **Indefinite** |
| `source-cache/` | Optional | Pipeline service role | 12 months after last access |

---

## 6. Normalized Condition Report Schema

Since condition reports come from three different platforms with different formats, the pipeline must normalize them into a unified VCH schema. Below is the target structure:

```json
{
  "vin": "1FTFW1E81PKE39204",
  "platform": "manheim",
  "auction_date": "2026-02-15T10:00:00Z",
  "lot_number": "12345678",
  "inspector_id": "MC-4521",
  "overall_grade": {
    "vch_normalized_grade": "B+",
    "platform_native_grade": "3.8",
    "platform_grade_scale": "1.0-5.0"
  },
  "exterior": {
    "summary": "Good overall condition with minor cosmetic wear",
    "panels": [
      {
        "location": "rear_bumper_driver",
        "finding": "Minor scratch, approximately 3 inches",
        "severity": "minor",
        "disclosure_image_refs": ["disclosure_001.jpg"]
      },
      {
        "location": "hood_center",
        "finding": "Two small stone chips",
        "severity": "minor",
        "disclosure_image_refs": ["disclosure_002.jpg"]
      }
    ]
  },
  "interior": {
    "summary": "Clean interior, normal wear for mileage",
    "findings": [
      {
        "location": "driver_seat",
        "finding": "Light wear on bolster, no tears",
        "severity": "normal_wear",
        "disclosure_image_refs": []
      }
    ]
  },
  "mechanical": {
    "summary": "No mechanical issues noted",
    "engine_starts": true,
    "transmission_shifts": true,
    "findings": []
  },
  "tires": {
    "front_left": {"tread_depth_32nds": 7, "condition": "good"},
    "front_right": {"tread_depth_32nds": 7, "condition": "good"},
    "rear_left": {"tread_depth_32nds": 6, "condition": "good"},
    "rear_right": {"tread_depth_32nds": 5, "condition": "fair"}
  },
  "glass": {
    "windshield": "No damage noted",
    "findings": []
  },
  "structural": {
    "frame_damage": false,
    "findings": []
  },
  "buyer_protection": {
    "program": "DealShield",
    "platform": "manheim",
    "eligible": true,
    "terms_summary": "Full return within 7 days if vehicle condition does not match CR.",
    "terms_url": "https://www.manheim.com/dealshield-terms"
  },
  "inspection_images": [
    {"filename": "inspection_001.jpg", "angle": "front_34", "type": "standard"},
    {"filename": "inspection_002.jpg", "angle": "rear_34", "type": "standard"},
    {"filename": "inspection_003.jpg", "angle": "driver_side", "type": "standard"},
    {"filename": "inspection_004.jpg", "angle": "passenger_side", "type": "standard"},
    {"filename": "inspection_005.jpg", "angle": "interior_front", "type": "standard"},
    {"filename": "inspection_006.jpg", "angle": "interior_rear", "type": "standard"},
    {"filename": "inspection_007.jpg", "angle": "engine", "type": "standard"},
    {"filename": "inspection_008.jpg", "angle": "odometer", "type": "standard"}
  ],
  "disclosure_images": [
    {
      "filename": "disclosure_001.jpg",
      "linked_finding": "exterior.panels[0]",
      "description": "Scratch on rear bumper, driver side"
    },
    {
      "filename": "disclosure_002.jpg",
      "linked_finding": "exterior.panels[1]",
      "description": "Stone chips on hood"
    }
  ]
}
```

**Normalization rules per platform:**

| Field | Manheim | OpenLane | Ally Smart Auction |
|---|---|---|---|
| Overall grade | Convert Manheim 1.0-5.0 scale to VCH letter grade | Convert OpenLane rating to VCH letter grade | Convert Ally rating to VCH letter grade |
| Panel locations | Map Manheim panel codes to VCH location enum | Map OpenLane panel codes to VCH location enum | Map Ally panel codes to VCH location enum |
| Severity levels | Map to: `minor`, `moderate`, `significant`, `normal_wear` | Same mapping | Same mapping |
| Buyer protection | DealShield terms | OpenLane Arbitration terms | Ally Return Protection terms |

**Agent note:** The exact mapping tables for each platform's condition report format into this normalized schema will need to be developed as we integrate each platform's data feed. Start with Manheim as the primary platform, then extend to OpenLane and Ally Smart Auction.

---

## 7. Image Display Priority Logic

### 7A. Public Browsing Pages (Search Results, Listing Grid)

```
ALWAYS USE:
  1. Tier 2 hero image (if available)
  2. FALLBACK: First photo_links_cached image with Tier 1 marketing CSS frame
```

### 7B. Vehicle Detail Page (Pre-Engagement)

```
HERO/THUMBNAIL: Tier 2 hero image
GALLERY: Original MarketCheck cached images with Tier 1 marketing CSS frame
```

### 7C. Vehicle Detail Page (Post-Engagement, Pre-Deal)

```
HERO/THUMBNAIL: Tier 2 hero image
GALLERY: Tier 3 processed images with Tier 1 marketing CSS frame
FALLBACK: Original MarketCheck cached images with Tier 1 marketing CSS frame
```

### 7D. "My Garage" Customer Portal (Deal in Progress)

```
PRIMARY TAB — "Vehicle Inspection Report":
  - Auction inspection images with Tier 1 MINIMAL CSS frame (light border only)
  - Normalized condition report with linked disclosure images
  - Buyer protection program details
  - Label: "Independent Inspection by [Platform Name]"

SECONDARY TAB — "Vehicle Photos":
  - Tier 3 processed images (or Tier 2/1 fallback) for general reference
  - Label: "Reference Photos"
  - Disclaimer: "These photos are for general reference and may not reflect
    the vehicle's exact current condition. Please refer to the Vehicle
    Inspection Report for verified condition details."

IF INSPECTION PENDING (dealer vehicle being moved to auction):
  - Show: "Vehicle Inspection In Progress"
  - Show: Tier 3/2/1 images as available with reference disclaimer
  - Set vehicle status indicator: "Pending Independent Inspection"
```

### 7E. Post-Purchase / Delivery Records

```
PERMANENT RECORD:
  - Auction inspection images (unmodified originals retrievable via S3)
  - Normalized condition report
  - Buyer protection details and terms
  - Hash verification available for any disputed image
```

---

## 8. Pipeline Event Summary

| Event | Path A (Dealer Listing) | Path B (Auction Discovered) |
|---|---|---|
| **VIN enters system** | Ingest MC images → cache in S3 → Tier 1 + queue Tier 2 | Store auction scrape data + query MC for backfill images → cache in S3 → Tier 1 + queue Tier 2 |
| **Hero image created** | Tier 2 on first exterior MC image | Same — uses MC-sourced exterior image |
| **Customer engages** | Tier 3 on all MC-sourced images | Same |
| **Deal initiates** | VCH moves vehicle to auction via Manheim Express / OpenLane / Ally → **vehicle enters Tier 4 pipeline** | Tier 4 — auction images and CR already exist or are incoming |
| **Auction inspection complete** | Tier 4 images + CR ingested → "My Garage" transitions to inspection view | Same |
| **Dispute arises** | Auction originals (unmodified, hash-verified) + normalized CR serve as evidence. Buyer protection program engaged. | Same |

**Key insight from this table:** Both paths converge at the deal stage. From the deal stage forward, every vehicle is handled identically because every vehicle is an auction vehicle.

---

## 9. Key Principles for the Building Agent

1. **Tier 1 is ALWAYS on.** Every image displayed on VirtualCarHub gets a CSS branded frame. Marketing contexts get the full frame; inspection/condition contexts get a minimal frame.

2. **Process once, serve forever.** The VIN dedup gate ensures we never waste compute on images we've already processed.

3. **Auction originals are sacred.** They are never modified, never deleted, always hash-verified. They are legal and business evidence used in arbitration through DealShield, OpenLane, or Ally Smart Auction protections.

4. **Cost scales with revenue, not inventory.** Tiers 3 and 4 only fire when customers are engaged or deals are progressing. Speculative processing is waste.

5. **The pipeline is source-agnostic for Tiers 1-3.** Once MarketCheck images enter the system from either Path A or Path B, Tiers 1-3 treat them identically. Tier 4 is universal — all deal-stage vehicles go through auction.

6. **Normalize the customer experience, preserve the platform specifics.** The customer sees a unified "VirtualCarHub Inspection Report" regardless of whether Manheim, OpenLane, or Ally Smart Auction inspected the vehicle. But the raw platform-specific data is always preserved underneath.

7. **Every vehicle gets inspected.** This is not optional. If a vehicle reaches the deal stage, it has been or will be inspected by a professional auction inspector. If the inspection hasn't happened yet (e.g., Manheim Express in progress), the customer portal shows "Pending Inspection" status.

8. **Fail gracefully.** If MarketCheck has no historical images for a VIN, create the listing with specs/description only and flag as "Photos Coming Soon." Do not block listing creation on image availability.

9. **Current verified condition wins.** When Tier 4 inspection images are available, they take primary display position because they represent what an independent inspector verified. Marketing images become secondary reference only.

10. **Three platforms, one experience.** The condition report normalization layer (Section 6) is what makes this possible. Build the normalization for Manheim first, then extend the same pattern to OpenLane and Ally Smart Auction.
