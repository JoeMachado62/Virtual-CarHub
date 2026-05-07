/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { AuthModal } from "@/components/AuthModal";
import { apiFetch } from "@/lib/api";
import { AuthState, canAccessConditionReports, clearAuthState, isAdminUser, loadValidAuthState } from "@/lib/auth";
import { normalizeSourceFilterValue, toPublicSourceLabel } from "@/lib/sourceLabels";
import { BODY_TYPE_OPTIONS } from "@/lib/vehicleOptions";
import { maskVin } from "@/lib/vin";

// Prefer the HMAC-derived public_slug for any public URL so the raw VIN
// never appears in the address bar. Legacy VIN fallback keeps things
// working for any row that hasn't been backfilled yet.
function publicIdentifier(item: { public_slug?: string | null; vin: string }): string {
  return item.public_slug || item.vin;
}

type DisplayMode = "MARKETING" | "INSPECTION_PENDING" | "INSPECTION_REPORT";
type InspectionStatus = "NOT_STARTED" | "PENDING" | "INGESTED" | "NORMALIZED" | "VERIFIED" | "FAILED";

type VehicleDisplayContext = {
  mode: DisplayMode;
  inspection_status: InspectionStatus;
  hero_image?: string | null;
  gallery_images?: string[];
  marketing_images?: string[];
  reference_images?: string[];
  reference_detail_images?: string[];
  reference_provider?: string | null;
  has_reference_stock?: boolean;
  reference_pending?: boolean;
  reference_color_exact?: boolean;
  imagin_images?: string[];
  spin_images?: string[];
  source_images?: string[];
  inspection_images?: string[];
  disclosure_images?: string[];
  has_inspection_report?: boolean;
  has_imagin_stock?: boolean;
  dealer_photos_gated?: boolean;
  gated_photo_count?: number;
  disclaimer?: string;
  condition_report?: Record<string, unknown>;
};

type InventoryItem = {
  vin: string;
  public_slug?: string | null;
  listing_id?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  drivetrain?: string | null;
  engine_type?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  transmission?: string | null;
  fuel_type?: string | null;
  odometer_units?: string | null;
  price_asking: number;
  odometer?: number | null;
  location_state?: string | null;
  location_zip?: string | null;
  source_type?: string | null;
  source_filter_value?: string | null;
  source_label?: string | null;
  source_url?: string | null;
  thumbnail?: string | null;
  reference_pending?: boolean;
  evox_pending?: boolean;
  dealer_photos_gated?: boolean;
  gated_photo_count?: number;
  images_count?: number;
  features_preview?: string[];
  display_mode?: DisplayMode;
  inspection_status?: InspectionStatus;
  has_inspection_report?: boolean;
  badges?: { type: string; label: string; color: string; ratio?: string }[];
  hot_deal?: {
    mmr_value: number;
    deal_delta: number;
    deal_label: string;
    auction_end_at: string;
  };
};

type HotDealFeedItem = {
  id: string;
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  price_asking: number;
  location_state?: string | null;
  location_zip?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  thumbnail?: string | null;
  deal_label: string;
  deal_delta: number;
  mmr_value: number;
  auction_end_at: string;
  vdp_path?: string | null;
  image_display_mode?: DisplayMode | null;
  inspection_status?: InspectionStatus | null;
  has_inspection_report?: boolean;
  reference_pending?: boolean;
  dealer_photos_gated?: boolean;
  gated_photo_count?: number;
};

type VehicleDetail = {
  vin: string;
  public_slug?: string | null;
  listing_id?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  sub_body_type?: string | null;
  engine_type?: string | null;
  cylinders?: number | null;
  forced_induction?: string | null;
  drivetrain?: string | null;
  mpg_combined?: number | null;
  ev_range?: number | null;
  towing_capacity_lbs?: number | null;
  odometer?: number | null;
  condition_grade?: string | null;
  price_asking: number;
  price_wholesale_est?: number | null;
  location_zip?: string | null;
  location_state?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  images: string[];
  display_images?: string[];
  hero_image?: string | null;
  display_mode?: DisplayMode;
  inspection_status?: InspectionStatus;
  has_inspection_report?: boolean;
  display_context?: VehicleDisplayContext;
  source_label?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  transmission?: string | null;
  fuel_type?: string | null;
  odometer_units?: string | null;
  auction_house?: string | null;
  pickup_location?: string | null;
  inventory_status?: string | null;
  inventory_label?: string | null;
  condition_report_grade?: string | null;
  seller_comments?: string | null;
  condition_report?: Record<string, unknown>;
  listing_snapshot?: Record<string, unknown>;
  ove_detail?: {
    source_platform?: string;
    page_url?: string | null;
    last_synced_at?: string | null;
  } | null;
  mmr?: number | null;
  badges?: { type: string; label: string; color: string; ratio?: string }[];
  features_raw: string[];
  features_normalized: Record<string, number>;
  available: boolean;
  last_seen_active?: string | null;
  updated_at?: string | null;
};

function QuickViewIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M1.5 12s3.8-6.5 10.5-6.5S22.5 12 22.5 12 18.7 18.5 12 18.5 1.5 12 1.5 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

type Pagination = {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
};

type SyncMeta = {
  requested: boolean;
  enabled: boolean;
  executed: boolean;
  mode: string;
  fetched: number;
  inserted: number;
  updated: number;
  skipped_priority: number;
  skipped_invalid: number;
  error?: string | null;
};

type InventorySearchPayload = {
  items: InventoryItem[];
  pagination: Pagination;
  sync?: SyncMeta;
};

type FacetBucket = {
  item: string;
  count: number;
};

type InventoryFacetPayload = {
  source: string;
  num_found: number;
  facets: Record<string, FacetBucket[]>;
  taxonomy: {
    source: string;
    years: FacetBucket[];
    make: FacetBucket[];
    model: FacetBucket[];
    trim: FacetBucket[];
    lookup?: {
      models_by_make?: Record<string, string[]>;
      trims_by_make_model?: Record<string, string[]>;
      body_types_by_make_model?: Record<string, string[]>;
      body_types_by_make_model_trim?: Record<string, string[]>;
    };
  };
};

type GarageItem = {
  id: string;
  vin: string;
  public_slug?: string | null;
  status: string;
  source: string;
  added_at: string;
  updated_at: string;
  acquisition_started_at?: string | null;
  deal_stage: string;
  display_mode: DisplayMode;
  inspection_status: InspectionStatus;
  has_inspection_report: boolean;
  display_context?: VehicleDisplayContext;
  vehicle: {
    year?: number | null;
    make?: string | null;
    model?: string | null;
    trim?: string | null;
    price_asking?: number | null;
    odometer?: number | null;
    location_state?: string | null;
    location_zip?: string | null;
    source_type?: string | null;
    thumbnail?: string | null;
  };
};

type FilterState = {
  q: string;
  make: string[];
  model: string[];
  trim: string[];
  body_type: string[];
  source_type: string;
  state: string;
  zip_code: string;
  radius: string;
  min_price: string;
  max_price: string;
  min_year: string;
  max_year: string;
  min_miles: string;
  max_miles: string;
  exterior_color: string[];
  interior_color: string[];
  has_images: boolean;
  live_sync: boolean;
  sort_by: "updated_at" | "price_asking" | "year" | "odometer";
  sort_dir: "asc" | "desc";
};

type SearchMode = "inventory" | "hot_deals";

const INITIAL_FILTERS: FilterState = {
  q: "",
  make: [],
  model: [],
  trim: [],
  body_type: [],
  source_type: "",
  state: "",
  zip_code: "",
  radius: "500",
  min_price: "",
  max_price: "",
  min_year: "",
  max_year: "",
  min_miles: "",
  max_miles: "",
  exterior_color: [],
  interior_color: [],
  has_images: false,
  live_sync: true,
  sort_by: "updated_at",
  sort_dir: "desc",
};

const EXTERIOR_COLOR_OPTIONS = [
  "White", "Black", "Gray", "Silver", "Blue", "Red", "Green", "Brown",
  "Beige/Tan", "Orange", "Yellow", "Gold", "Purple", "Burgundy/Maroon",
  "Bronze", "Turquoise/Teal", "Other",
];

const INTERIOR_COLOR_OPTIONS = [
  "Black", "Gray", "Beige/Tan", "Brown", "White/Ivory", "Red", "Blue",
  "Green", "Orange", "Burgundy/Maroon", "Other",
];

const STACKED_INVENTORY_QUERY = "(max-width: 1080px)";

const FACET_REFRESH_KEYS: (keyof FilterState)[] = [
  "q",
  "make",
  "model",
  "trim",
  "source_type",
  "state",
  "zip_code",
  "radius",
  "min_price",
  "max_price",
  "min_year",
  "max_year",
  "min_miles",
  "max_miles",
  "exterior_color",
  "interior_color",
  "has_images",
];

const EMPTY_PAGINATION: Pagination = {
  page: 1,
  per_page: 18,
  total: 0,
  total_pages: 0,
  has_next: false,
  has_prev: false,
};

const EMPTY_SYNC: SyncMeta = {
  requested: false,
  enabled: false,
  executed: false,
  mode: "disabled",
  fetched: 0,
  inserted: 0,
  updated: 0,
  skipped_priority: 0,
  skipped_invalid: 0,
  error: null,
};

const FALLBACK_IMAGE = "/assets/images/portfolio/VCH Auction default image.webp";
const SHOWROOM_BG = "/assets/images/portfolio/vch-showroom.webp";

const _EXTERIOR_SHOTS = new Set(["01", "02", "03", "05", "06", "07"]);

function _extractShot(url: string): string | null {
  const m = url.match(/_(\d{2})\.\w{3,4}$/);
  return m ? m[1] : null;
}

function isChromeDataExterior(url: string | null | undefined): boolean {
  if (!url || !url.includes("media.chromedata.com")) return false;
  const shot = _extractShot(url);
  return !shot || _EXTERIOR_SHOTS.has(shot);
}

function isSideProfile(url: string | null | undefined): boolean {
  if (!url) return false;
  return _extractShot(url) === "03";
}

function showroomContainerStyle(url: string | null | undefined): React.CSSProperties | undefined {
  if (!isChromeDataExterior(url)) return undefined;
  return {
    background: `url(${SHOWROOM_BG}) center bottom / cover no-repeat`,
  };
}

function showroomImageStyle(url: string | null | undefined): React.CSSProperties | undefined {
  if (!isChromeDataExterior(url)) return undefined;
  return {
    objectFit: "contain",
    objectPosition: "center bottom",
    transformOrigin: "center bottom",
  };
}

function showroomImageClassName(url: string | null | undefined): string | undefined {
  if (!isChromeDataExterior(url)) return undefined;
  return isSideProfile(url) ? "inventory-showroom-image inventory-showroom-image-side" : "inventory-showroom-image";
}
const SEARCH_CONTEXT_KEY = "vch:inventory:search-context";
const SEARCH_FILTERS_KEY = "vch:inventory:filters";
const SEARCH_FILTERS_LOCAL_KEY = "vch:inventory:last-filters";
const SEARCH_RESULTS_CACHE_KEY = "vch:inventory:results-cache";
const SEARCH_RESULTS_CACHE_TTL_MS = 10 * 60 * 1000;
const HOT_DEALS_CACHE_KEY = "vch:inventory:hot-deals-cache:v2";
const HOT_DEALS_CACHE_TTL_MS = 5 * 60 * 1000;
const LIVE_SYNC_FALLBACK_MESSAGE = "Current wholesale updates are temporarily unavailable. Showing saved inventory results.";

const PROGRESS_MESSAGES = [
  "Checking surplus inventory listings",
  "Contacting wholesale sources",
  "Scanning dealer networks",
  "Vetting inventory quality",
  "Verifying vehicle history",
  "Matching factory specifications",
  "Preparing color-matched images",
  "Validating pricing information",
  "Cross-referencing market data",
  "Finalizing listing details",
];
const PROGRESS_STEP_MS = 6200;
const PROGRESS_DOT_MS = 650;

function SearchProgressOverlay() {
  const [step, setStep] = useState(0);
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev < PROGRESS_MESSAGES.length - 1 ? prev + 1 : prev));
      setDotCount(1);
    }, PROGRESS_STEP_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setDotCount((prev) => (prev >= 4 ? 1 : prev + 1));
    }, PROGRESS_DOT_MS);
    return () => clearInterval(interval);
  }, []);

  const pct = Math.min(((step + 1) / PROGRESS_MESSAGES.length) * 100, 95);
  const dots = ".".repeat(dotCount);

  return (
    <div className="card" style={{ textAlign: "center", padding: "3rem 2rem" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <svg width="48" height="48" viewBox="0 0 48 48" style={{ animation: "spin 1.2s linear infinite" }}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="var(--accent, #3b82f6)" strokeWidth="4" strokeDasharray="90 40" strokeLinecap="round" />
        </svg>
      </div>
      <h3 style={{ margin: "0 0 0.75rem", fontSize: "1.15rem" }}>Searching Wholesale Inventory</h3>
      <p style={{ margin: "0 0 1.5rem", opacity: 0.8, minHeight: "1.4em", transition: "opacity 0.3s" }}>
        {PROGRESS_MESSAGES[step]}{dots}
      </p>
      <div style={{ background: "rgba(255,255,255,0.1)", borderRadius: 8, height: 6, overflow: "hidden", maxWidth: 320, margin: "0 auto" }}>
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: "var(--accent, #3b82f6)",
            borderRadius: 8,
            transition: "width 0.8s ease",
          }}
        />
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function sanitizeSyncWarning(message?: string | null): string | null {
  if (!message) return null;
  const normalized = message.toLowerCase();
  if (
    normalized.includes("api.marketcheck.com") ||
    normalized.includes("client error") ||
    normalized.includes("for url") ||
    normalized.includes("api_key=")
  ) {
    return LIVE_SYNC_FALLBACK_MESSAGE;
  }
  return message;
}

type InventoryExplorerProps = {
  initialMake?: string;
  initialModel?: string;
  initialTrim?: string;
};

function mergeFacetOptions(base: FacetBucket[] = [], counted: FacetBucket[] = []): FacetBucket[] {
  const seen = new Set<string>();
  const byKey = new Map(counted.map((item) => [item.item.toLowerCase(), item]));
  const merged: FacetBucket[] = [];

  counted.forEach((item) => {
    const key = item.item.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(item);
  });

  base.forEach((item) => {
    const key = item.item.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(byKey.get(key) || item);
  });

  return merged;
}

function optionBuckets(values: string[], counted: FacetBucket[] = []): { item: string; count?: number }[] {
  const counts = new Map(counted.map((item) => [item.item.toLowerCase(), item.count]));
  const seen = new Set<string>();
  return values
    .filter((value) => {
      const key = value.toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => a.localeCompare(b))
    .map((item) => ({ item, count: counts.get(item.toLowerCase()) }));
}

function hasSelectedBodyType(
  bodyTypesByKey: Record<string, string[]> | undefined,
  key: string,
  selectedBodyTypes: string[],
): boolean {
  if (selectedBodyTypes.length === 0) return true;
  const available = bodyTypesByKey?.[key];
  if (!available || available.length === 0) return false;
  const selected = new Set(selectedBodyTypes.map((value) => value.toLowerCase()));
  return available.some((value) => selected.has(value.toLowerCase()));
}

function makeModelPairKey(make: string, model: string): string {
  return `${make}|||${model}`;
}

function makeModelTrimKey(make: string, model: string, trim: string): string {
  return `${makeModelPairKey(make, model)}|||${trim}`;
}

function buildModelOptions(
  taxonomy: InventoryFacetPayload["taxonomy"] | null,
  facets: Record<string, FacetBucket[]>,
  filters: FilterState,
): { item: string; count?: number }[] {
  const lookup = taxonomy?.lookup;
  const modelsByMake = lookup?.models_by_make || {};
  const selectedMakes = new Set(filters.make.map((value) => value.toLowerCase()));
  const selectedBodyTypes = filters.body_type.length > 0;
  const facetModels = facets.model || [];
  const models = selectedBodyTypes && facetModels.length > 0 ? facetModels.map((bucket) => bucket.item) : [];

  if (!selectedBodyTypes || facetModels.length === 0) {
    Object.entries(modelsByMake).forEach(([make, values]) => {
      if (selectedMakes.size > 0 && !selectedMakes.has(make.toLowerCase())) return;
      values.forEach((model) => {
        const key = makeModelPairKey(make, model);
        if (hasSelectedBodyType(lookup?.body_types_by_make_model, key, filters.body_type)) {
          models.push(model);
        }
      });
    });
  }

  if (models.length === 0) {
    return selectedBodyTypes ? facetModels : mergeFacetOptions(taxonomy?.model || [], facetModels);
  }
  return optionBuckets(models, facetModels);
}

function buildTrimOptions(
  taxonomy: InventoryFacetPayload["taxonomy"] | null,
  facets: Record<string, FacetBucket[]>,
  filters: FilterState,
): { item: string; count?: number }[] {
  const lookup = taxonomy?.lookup;
  const trimsByMakeModel = lookup?.trims_by_make_model || {};
  const selectedMakes = new Set(filters.make.map((value) => value.toLowerCase()));
  const selectedModels = new Set(filters.model.map((value) => value.toLowerCase()));
  const trims: string[] = [];

  Object.entries(trimsByMakeModel).forEach(([key, values]) => {
    const [make, model] = key.split("|||");
    if (!make || !model) return;
    if (selectedMakes.size > 0 && !selectedMakes.has(make.toLowerCase())) return;
    if (selectedModels.size > 0 && !selectedModels.has(model.toLowerCase())) return;
    values.forEach((trim) => {
      const trimKey = makeModelTrimKey(make, model, trim);
      if (hasSelectedBodyType(lookup?.body_types_by_make_model_trim, trimKey, filters.body_type)) {
        trims.push(trim);
      }
    });
  });

  if (trims.length === 0) {
    return mergeFacetOptions(taxonomy?.trim || [], facets.trim || []);
  }
  return optionBuckets(trims, facets.trim || []);
}

function buildMakeModelPairs(
  taxonomy: InventoryFacetPayload["taxonomy"] | null,
  filters: FilterState,
): string[] {
  if (filters.make.length === 0 || filters.model.length === 0) return [];
  const lookup = taxonomy?.lookup?.models_by_make || {};
  const selectedMakes = new Set(filters.make.map((value) => value.toLowerCase()));
  const selectedModels = new Set(filters.model.map((value) => value.toLowerCase()));
  const pairs: string[] = [];

  Object.entries(lookup).forEach(([make, models]) => {
    if (!selectedMakes.has(make.toLowerCase())) return;
    models.forEach((model) => {
      if (selectedModels.has(model.toLowerCase())) {
        pairs.push(makeModelPairKey(make, model));
      }
    });
  });

  if (pairs.length > 0) return pairs;
  return filters.make.flatMap((make) => filters.model.map((model) => makeModelPairKey(make, model)));
}

function mapHotDealToInventoryItem(item: HotDealFeedItem): InventoryItem {
  return {
    vin: item.vin,
    public_slug: item.public_slug,
    year: item.year,
    make: item.make,
    model: item.model,
    trim: item.trim,
    price_asking: item.price_asking,
    location_state: item.location_state,
    location_zip: item.location_zip,
    source_type: item.source_type || "ove",
    source_filter_value: "auction",
    source_label: item.source_label || "Hot Deal",
    thumbnail: item.thumbnail,
    images_count: item.thumbnail ? 1 : 0,
    reference_pending: Boolean(item.reference_pending),
    dealer_photos_gated: Boolean(item.dealer_photos_gated),
    gated_photo_count: item.gated_photo_count || 0,
    display_mode: item.image_display_mode || "MARKETING",
    inspection_status: item.inspection_status || "VERIFIED",
    has_inspection_report: Boolean(item.has_inspection_report),
    badges: [
      {
        type: "hot_deal",
        label: `${item.deal_label || "Hot"} Deal`,
        color: "green",
      },
      {
        type: "deal_delta",
        label: `${formatMoney(item.deal_delta)} below MMR`,
        color: "orange",
      },
    ],
    hot_deal: {
      mmr_value: item.mmr_value,
      deal_delta: item.deal_delta,
      deal_label: item.deal_label,
      auction_end_at: item.auction_end_at,
    },
  };
}

function MultiSelectList({
  label,
  options,
  selected,
  onChange,
  maxVisible = 80,
  showLabel = true,
}: {
  label: string;
  options: { item: string; count?: number }[];
  selected: string[];
  onChange: (next: string[]) => void;
  maxVisible?: number;
  showLabel?: boolean;
}) {
  const normalizedSelected = useMemo(() => new Set(selected), [selected]);
  const visibleOptions = useMemo(() => {
    const seen = new Set<string>();
    const merged: { item: string; count?: number }[] = [];

    selected.forEach((value) => {
      const match = options.find((opt) => opt.item.toLowerCase() === value);
      seen.add(value);
      merged.push(match || { item: value });
    });

    options.forEach((opt) => {
      const key = opt.item.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(opt);
    });

    return merged.slice(0, maxVisible);
  }, [maxVisible, options, selected]);

  function toggle(value: string) {
    const lower = value.toLowerCase();
    if (selected.includes(lower)) {
      onChange(selected.filter((s) => s !== lower));
    } else {
      onChange([...selected, lower]);
    }
  }
  return (
    <label>
      {showLabel ? (
        <>
          {label}
          {selected.length > 0 && <span className="multi-select-count">{selected.length}</span>}
        </>
      ) : null}
      <div className="multi-select-list">
        {visibleOptions.length === 0 && <span className="multi-select-empty">No options available</span>}
        {visibleOptions.map((opt) => (
          <button
            key={opt.item}
            type="button"
            className={`multi-select-item${normalizedSelected.has(opt.item.toLowerCase()) ? " selected" : ""}`}
            onClick={() => toggle(opt.item)}
            title={opt.item}
          >
            <span>{opt.item}</span>
            {opt.count != null ? <small>{opt.count.toLocaleString()}</small> : null}
          </button>
        ))}
      </div>
    </label>
  );
}

function ChevronDownIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`filter-section-icon${open ? " open" : ""}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="m6 9 6 6 6-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FilterSection({
  id,
  title,
  selectedCount = 0,
  openId,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  selectedCount?: number;
  openId: string | null;
  onToggle: (id: string) => void;
  children: ReactNode;
}) {
  const open = openId === id;

  return (
    <section className={`filter-section${open ? " open" : ""}`}>
      <button className="filter-section-trigger" type="button" onClick={() => onToggle(id)} aria-expanded={open}>
        <span>
          {title}
          {selectedCount > 0 && <span className="multi-select-count">{selectedCount}</span>}
        </span>
        <ChevronDownIcon open={open} />
      </button>
      {open ? <div className="filter-section-body">{children}</div> : null}
    </section>
  );
}

export function InventoryExplorer({ initialMake, initialModel, initialTrim }: InventoryExplorerProps = {}) {
  const searchParams = useSearchParams();
  const resultsRef = useRef<HTMLElement | null>(null);
  const hasInitializedFiltersRef = useRef(false);
  const inventoryRequestSeqRef = useRef(0);
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>("inventory");
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingActionType, setPendingActionType] = useState<"garage" | "remove" | "acquire" | "cr" | null>(null);
  const [pendingActionVin, setPendingActionVin] = useState<string | null>(null);

  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [filtersReady, setFiltersReady] = useState(false);
  const [readyToSearchMessage, setReadyToSearchMessage] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<InventoryItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>(EMPTY_PAGINATION);
  const [syncMeta, setSyncMeta] = useState<SyncMeta>(EMPTY_SYNC);
  const [taxonomy, setTaxonomy] = useState<InventoryFacetPayload["taxonomy"] | null>(null);
  const [facets, setFacets] = useState<Record<string, FacetBucket[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedVin, setSelectedVin] = useState<string | null>(null);
  const [detailsByVin, setDetailsByVin] = useState<Record<string, VehicleDetail>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const [garageItems, setGarageItems] = useState<GarageItem[]>([]);
  const [garageLoading, setGarageLoading] = useState(false);
  const [isPreapproved, setIsPreapproved] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [openFilter, setOpenFilter] = useState<string | null>(null);
  const [garageActionVin, setGarageActionVin] = useState<string | null>(null);
  const [garageError, setGarageError] = useState<string | null>(null);
  const [garageNotice, setGarageNotice] = useState<string | null>(null);
  const [pendingResultsScroll, setPendingResultsScroll] = useState(false);

  const facetRefreshKey = useMemo(
    () =>
      FACET_REFRESH_KEYS.map((key) => {
        const value = filters[key];
        return Array.isArray(value) ? value.join(",") : String(value);
      }).join("|"),
    [filters],
  );

  const bodyTypeOptions = useMemo(
    () => {
      const staticBuckets: FacetBucket[] = BODY_TYPE_OPTIONS.map((bt) => ({ item: bt, count: 0 }));
      return mergeFacetOptions(staticBuckets, facets.body_type || []);
    },
    [facets.body_type],
  );

  const makeOptions = useMemo(
    () => mergeFacetOptions(taxonomy?.make || [], facets.make || []),
    [facets.make, taxonomy?.make],
  );

  const modelOptions = useMemo(
    () => buildModelOptions(taxonomy, facets, filters),
    [facets, filters, taxonomy],
  );

  const trimOptions = useMemo(
    () => buildTrimOptions(taxonomy, facets, filters),
    [facets, filters, taxonomy],
  );

  function toggleFilterSection(id: string) {
    setOpenFilter((current) => (current === id ? null : id));
  }

  function isStackedInventoryLayout() {
    return typeof window !== "undefined" && window.matchMedia(STACKED_INVENTORY_QUERY).matches;
  }

  function queueMobileResultsScroll() {
    if (!isStackedInventoryLayout()) return;
    setPendingResultsScroll(true);
  }

  function scrollMobileResultsIntoView(behavior: ScrollBehavior = "smooth") {
    if (!isStackedInventoryLayout()) return;
    window.setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior, block: "start" });
    }, 120);
  }

  function collapseMobileFilters() {
    if (!isStackedInventoryLayout()) return;
    setFiltersOpen(false);
    setOpenFilter(null);
  }

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (cancelled) return;
      try {
        const saved = await loadValidAuthState();
        if (!cancelled) setAuth(saved);
      } finally {
        if (!cancelled) setAuthChecked(true);
      }
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    let cancelled = false;

    // Helper: split comma-separated URL param into lowercased array
    const csvToArr = (v: string | null) => (v || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    const hasVehicleIntentFilters = (candidate: Partial<FilterState>) =>
      Boolean(
        candidate.make?.length || candidate.model?.length || candidate.trim?.length || candidate.body_type?.length ||
        candidate.exterior_color?.length || candidate.interior_color?.length || candidate.q ||
        candidate.min_year || candidate.max_year || candidate.min_price || candidate.max_price ||
        candidate.min_miles || candidate.max_miles
      );
    const normalizeRestoredFilters = (restored: FilterState) => {
      for (const k of ["make", "model", "trim", "body_type", "exterior_color", "interior_color"] as const) {
        if (typeof restored[k] === "string") {
          (restored as Record<string, unknown>)[k] = (restored[k] as unknown as string).split(",").filter(Boolean);
        }
      }
      return restored;
    };
    const readStoredFilters = (): FilterState | null => {
      const savedFilters =
        window.sessionStorage.getItem(SEARCH_FILTERS_KEY) ||
        window.localStorage.getItem(SEARCH_FILTERS_LOCAL_KEY);
      return savedFilters ? normalizeRestoredFilters(JSON.parse(savedFilters) as FilterState) : null;
    };
    const applyInitialFilters = (
      nextFilters: FilterState,
      mode: SearchMode = "inventory",
      options: { autoLoad?: boolean; message?: string } = {},
    ) => {
      if (cancelled) return;
      hasInitializedFiltersRef.current = true;
      const autoLoad = options.autoLoad ?? mode === "hot_deals";
      setSearchMode(mode);
      setFilters(nextFilters);
      setAppliedFilters(nextFilters);
      setFiltersReady(autoLoad);
      setReadyToSearchMessage(autoLoad ? null : options.message || "Review the selected filters, then click Search to load matching inventory.");
      if (!autoLoad) {
        setRows([]);
        setPagination(EMPTY_PAGINATION);
        setSyncMeta(EMPTY_SYNC);
        setError(null);
      }
    };

    // SEO route props take priority when no explicit URL search params are set
    if (initialMake && !searchParams.has("make")) {
      const nextFilters: FilterState = {
        ...INITIAL_FILTERS,
        make: [initialMake.toLowerCase()],
        ...(initialModel ? { model: [initialModel.toLowerCase()] } : {}),
        ...(initialTrim ? { trim: [initialTrim.toLowerCase()] } : {}),
      };
      applyInitialFilters(nextFilters, "inventory", {
        autoLoad: false,
        message: "Review the selected route filters, then click Search to load matching inventory.",
      });
      return;
    }

    // Check if URL has search params (from NLP, DealBuilder, etc.)
    const hasUrlParams = Array.from(searchParams.keys()).some(
      (k) => !["nlp_query"].includes(k) && searchParams.get(k),
    );
    const hasRouteFilters = Boolean(initialMake);

    if (hasInitializedFiltersRef.current && !hasUrlParams && !hasRouteFilters) {
      return;
    }

    if (hasUrlParams) {
      if (searchParams.get("hot_deals") === "true") {
        applyInitialFilters({ ...INITIAL_FILTERS, live_sync: false, sort_by: "updated_at", sort_dir: "desc" }, "hot_deals");
        scrollMobileResultsIntoView("auto");
        return;
      }

      // ── URL params present: build filters from URL ──
      const vinParam = searchParams.get("vin") || "";
      const q = vinParam || searchParams.get("q") || "";
      const sourceType = normalizeSourceFilterValue(searchParams.get("source_type"));
      const make = csvToArr(searchParams.get("make"));
      const model = csvToArr(searchParams.get("model"));
      const trim = csvToArr(searchParams.get("trim"));
      const bodyType = csvToArr(searchParams.get("body_type"));
      const minYear = searchParams.get("min_year") || "";
      const maxYear = searchParams.get("max_year") || "";
      const minPrice = searchParams.get("min_price") || "";
      const maxPrice = searchParams.get("max_price") || "";
      const minMiles = searchParams.get("min_miles") || "";
      const maxMiles = searchParams.get("max_miles") || "";
      const exteriorColor = csvToArr(searchParams.get("exterior_color"));
      const interiorColor = csvToArr(searchParams.get("interior_color"));
      const state = searchParams.get("state") || "";
      const zipCode = searchParams.get("zip_code") || "";

      // Preserve localStorage zip if none provided in URL
      let resolvedZip = zipCode;
      if (!resolvedZip) {
        try {
          const raw = window.localStorage.getItem(SEARCH_CONTEXT_KEY);
          if (raw) {
            const stored = JSON.parse(raw) as Partial<Pick<FilterState, "zip_code">>;
            resolvedZip = stored.zip_code || "";
          }
        } catch { /* ignore */ }
      }

      const nextFilters: FilterState = {
        ...INITIAL_FILTERS,
        q,
        source_type: sourceType,
        make,
        model,
        trim,
        body_type: bodyType,
        min_year: minYear,
        max_year: maxYear,
        min_price: minPrice,
        max_price: maxPrice,
        min_miles: minMiles,
        max_miles: maxMiles,
        exterior_color: exteriorColor,
        interior_color: interiorColor,
        state,
        ...(resolvedZip ? { zip_code: resolvedZip } : {}),
      };
      applyInitialFilters(nextFilters, "inventory", {
        autoLoad: false,
        message: "Review the selected filters, then click Search to load matching inventory.",
      });
      return;
    }

    void (async () => {
      // ── Restore cached search results (e.g. back-navigation from VDP) ──
      try {
        const cachedResults = window.sessionStorage.getItem(SEARCH_RESULTS_CACHE_KEY);
        if (cachedResults) {
          const parsed = JSON.parse(cachedResults) as {
            cached_at?: number;
            items?: InventoryItem[];
            pagination?: typeof EMPTY_PAGINATION;
            filters?: FilterState;
            page?: number;
          };
          if (
            parsed.cached_at &&
            Date.now() - parsed.cached_at < SEARCH_RESULTS_CACHE_TTL_MS &&
            Array.isArray(parsed.items) &&
            parsed.filters
          ) {
            const restored = normalizeRestoredFilters(parsed.filters);
            if (cancelled) return;
            setSearchMode("inventory");
            setFilters(restored);
            setAppliedFilters(restored);
            setRows(parsed.items);
            setPagination(parsed.pagination || EMPTY_PAGINATION);
            setSyncMeta(EMPTY_SYNC);
            setFiltersReady(true);
            setReadyToSearchMessage(null);
            setPage(parsed.page || 1);
            void loadFacets(restored);
            return;
          }
        }
      } catch { /* ignore stale cache */ }

      if (auth?.accessToken) {
        try {
          const res = await apiFetch<{
            bfv_json: Record<string, unknown> | null;
            is_complete: boolean;
          }>("/me/profile", {}, auth.accessToken);
          if (!cancelled && res.status === "ok" && res.data?.bfv_json && res.data.is_complete) {
            const bfv = res.data.bfv_json;
            const toArr = (v: unknown) =>
              Array.isArray(v) ? v.map((s) => String(s).toLowerCase()) : [];
            let storedFilters: FilterState | null = null;
            try {
              storedFilters = readStoredFilters();
            } catch { /* ignore invalid saved filters */ }
            const profileFilters: FilterState = {
              ...INITIAL_FILTERS,
              radius: storedFilters?.radius || INITIAL_FILTERS.radius,
              source_type: normalizeSourceFilterValue(storedFilters?.source_type),
              has_images: storedFilters?.has_images ?? INITIAL_FILTERS.has_images,
              live_sync: storedFilters?.live_sync ?? INITIAL_FILTERS.live_sync,
              sort_by: storedFilters?.sort_by || INITIAL_FILTERS.sort_by,
              sort_dir: storedFilters?.sort_dir || INITIAL_FILTERS.sort_dir,
            };
            if (storedFilters?.zip_code) profileFilters.zip_code = storedFilters.zip_code;
            if (bfv.delivery_zip) profileFilters.zip_code = String(bfv.delivery_zip);
            if (bfv.year_min) profileFilters.min_year = String(bfv.year_min);
            if (bfv.year_max) profileFilters.max_year = String(bfv.year_max);
            if (bfv.budget_min) profileFilters.min_price = String(bfv.budget_min);
            if (bfv.budget_max) profileFilters.max_price = String(bfv.budget_max);
            if (bfv.mileage_min) profileFilters.min_miles = String(bfv.mileage_min);
            if (bfv.mileage_max) profileFilters.max_miles = String(bfv.mileage_max);
            const bodyTypes = toArr(bfv.body_types_included);
            if (bodyTypes.length) profileFilters.body_type = bodyTypes;
            const brands = toArr(bfv.brands_included);
            if (brands.length) profileFilters.make = brands;
            if (profileFilters.zip_code && hasVehicleIntentFilters(profileFilters)) {
              applyInitialFilters(profileFilters, "inventory", {
                autoLoad: false,
                message: "Your Quick Match profile has prefilled the filters. Review them, then click Search to load inventory.",
              });
              return;
            }
          }
        } catch { /* profile fetch is best-effort */ }

        try {
          const restored = readStoredFilters();
          if (restored) {
            if (hasVehicleIntentFilters(restored)) {
              applyInitialFilters(restored, "inventory", {
                autoLoad: false,
                message: "Your last selected filters are ready. Review them, then click Search to load inventory.",
              });
              return;
            }
          }
        } catch { /* ignore */ }
      }

      applyInitialFilters({ ...INITIAL_FILTERS, live_sync: false }, "hot_deals");
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, authChecked, auth?.accessToken]);

  useEffect(() => {
    void loadFacets(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facetRefreshKey]);

  useEffect(() => {
    if (!filtersReady) return;
    void loadInventory(appliedFilters, page, searchMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersReady, appliedFilters, page, searchMode]);

  useEffect(() => {
    if (!pendingResultsScroll || loading) return;
    if (!isStackedInventoryLayout()) {
      setPendingResultsScroll(false);
      return;
    }

    const timer = window.setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setPendingResultsScroll(false);
    }, 80);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingResultsScroll, loading, rows.length, error, pagination.page]);

  // Lazy-fetch factory reference thumbnails once rows land.
  useEffect(() => {
    const pendingVins = rows.filter((r) => r.reference_pending || r.evox_pending).map((r) => r.vin);
    if (pendingVins.length === 0) return;

    let cancelled = false;
    async function fetchReferenceBatch() {
      try {
        const resp = await apiFetch<{ results: Record<string, { hero_url: string; gallery_urls: string[] }> }>(
          "/inventory/reference-images/batch",
          { method: "POST", body: JSON.stringify({ vins: pendingVins.slice(0, 10) }) },
        );
        if (cancelled || resp.status !== "ok" || !resp.data?.results) return;
        const results = resp.data.results;
        setRows((prev) =>
          prev.map((item) => {
            const reference = results[item.vin];
            if (!reference) return item;
            return { ...item, thumbnail: reference.hero_url, reference_pending: false, evox_pending: false };
          }),
        );
      } catch {
        // Non-critical: keep the existing thumbnail if the reference fetch fails.
      }
    }

    void fetchReferenceBatch();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows.map((r) => r.vin).join(",")]);

  useEffect(() => {
    if (auth?.accessToken) {
      void loadGarage(auth.accessToken);
      void loadAccountStatus(auth.accessToken);
    } else {
      setGarageItems([]);
      setGarageError(null);
      setIsPreapproved(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.accessToken]);

  useEffect(() => {
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeModal();
      }
    }
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, []);

  function signOut() {
    clearAuthState();
    setAuth(null);
  }

  function handleUnauthorized(response: { error: { code: string; message: string } | null }): boolean {
    if (response.error?.code !== "HTTP_401") return false;
    signOut();
    setGarageNotice(null);
    setGarageError("Your session expired. Sign in again from My Garage.");
    return true;
  }

  function persistSearchContext(nextFilters: FilterState) {
    try {
      window.localStorage.setItem(
        SEARCH_CONTEXT_KEY,
        JSON.stringify({
          zip_code: nextFilters.zip_code,
          radius: nextFilters.radius || "500",
        })
      );
      // Save full filter state to sessionStorage so it survives navigation
      window.sessionStorage.setItem(SEARCH_FILTERS_KEY, JSON.stringify(nextFilters));
      window.localStorage.setItem(SEARCH_FILTERS_LOCAL_KEY, JSON.stringify(nextFilters));
    } catch {
      return;
    }
  }

  function updateFilters(updater: (current: FilterState) => FilterState) {
    setFilters((current) => {
      const next = updater(current);
      persistSearchContext(next);
      return next;
    });
  }

  async function loadFacets(currentFilters: FilterState) {
    const params = new URLSearchParams();
    if (currentFilters.q.trim()) params.set("q", currentFilters.q.trim());
    if (currentFilters.make.length) params.set("make", currentFilters.make.join(","));
    if (currentFilters.min_price.trim()) params.set("min_price", currentFilters.min_price.trim());
    if (currentFilters.max_price.trim()) params.set("max_price", currentFilters.max_price.trim());
    if (currentFilters.min_year.trim()) params.set("min_year", currentFilters.min_year.trim());
    if (currentFilters.max_year.trim()) params.set("max_year", currentFilters.max_year.trim());
    if (currentFilters.min_miles.trim()) params.set("min_miles", currentFilters.min_miles.trim());
    if (currentFilters.max_miles.trim()) params.set("max_miles", currentFilters.max_miles.trim());
    // NOTE: body_type is intentionally NOT sent to the facets endpoint.
    // Sending it causes self-filtering: the backend restricts the dataset to the
    // selected body types before counting, which hides all other body type choices
    // and deflates make/model counts.  Body type filtering is still applied at
    // actual search time via loadInventory().
    if (currentFilters.exterior_color.length) params.set("exterior_color", currentFilters.exterior_color.join(","));
    if (currentFilters.interior_color.length) params.set("interior_color", currentFilters.interior_color.join(","));
    if (currentFilters.state.trim()) params.set("state", currentFilters.state.trim().toUpperCase());
    if (currentFilters.source_type.trim()) {
      params.set("source_type", normalizeSourceFilterValue(currentFilters.source_type));
    }
    if (currentFilters.zip_code.trim()) params.set("zip_code", currentFilters.zip_code.trim());
    if (currentFilters.radius.trim()) params.set("radius", currentFilters.radius.trim());
    params.set("has_images", currentFilters.has_images ? "true" : "false");
    params.set("use_marketcheck", "false");

    const response = await apiFetch<InventoryFacetPayload>(`/inventory/facets?${params.toString()}`);
    if (response.status !== "ok") {
      return;
    }
    setTaxonomy(response.data.taxonomy);
    setFacets(response.data.facets || {});
  }

  async function loadInventory(currentFilters: FilterState, currentPage: number, mode: SearchMode = searchMode) {
    const requestSeq = inventoryRequestSeqRef.current + 1;
    inventoryRequestSeqRef.current = requestSeq;
    const isCurrentRequest = () => inventoryRequestSeqRef.current === requestSeq;

    setLoading(true);
    setError(null);

    if (mode === "hot_deals") {
      try {
        const cached = window.sessionStorage.getItem(HOT_DEALS_CACHE_KEY);
        if (cached) {
          const parsed = JSON.parse(cached) as { cached_at?: number; items?: HotDealFeedItem[] };
          if (parsed.cached_at && Date.now() - parsed.cached_at < HOT_DEALS_CACHE_TTL_MS && Array.isArray(parsed.items)) {
            if (!isCurrentRequest()) return;
            const cachedRows = parsed.items.map(mapHotDealToInventoryItem);
            setRows(cachedRows);
            setPagination({ page: 1, per_page: cachedRows.length || 18, total: cachedRows.length, total_pages: cachedRows.length ? 1 : 0, has_next: false, has_prev: false });
            setSyncMeta(EMPTY_SYNC);
            setLoading(false);
            return;
          }
        }
      } catch { /* ignore stale cache */ }

      const response = await apiFetch<{ items: HotDealFeedItem[] }>("/inventory/hot-deals/active?limit=50");
      if (!isCurrentRequest()) return;
      if (response.status !== "ok") {
        setRows([]);
        setPagination(EMPTY_PAGINATION);
        setSyncMeta(EMPTY_SYNC);
        setError(response.error?.message || "Failed to load Hot Deals.");
        setLoading(false);
        return;
      }
      const items = response.data.items || [];
      if (items.length) {
        try {
          window.sessionStorage.setItem(HOT_DEALS_CACHE_KEY, JSON.stringify({ cached_at: Date.now(), items }));
        } catch { /* ignore cache failures */ }
      }
      const mappedRows = items.map(mapHotDealToInventoryItem);
      setRows(mappedRows);
      setPagination({ page: 1, per_page: mappedRows.length || 18, total: mappedRows.length, total_pages: mappedRows.length ? 1 : 0, has_next: false, has_prev: false });
      setSyncMeta(EMPTY_SYNC);
      setLoading(false);
      return;
    }

    // VIN searches (17 alphanumeric chars) bypass zip/radius requirement
    const qTrimmed = currentFilters.q.trim();
    const isVinSearch = qTrimmed.length === 17 && /^[A-Za-z0-9]+$/.test(qTrimmed);

    if (!isVinSearch && (!currentFilters.zip_code.trim() || !currentFilters.radius.trim())) {
      setRows([]);
      setPagination(EMPTY_PAGINATION);
      setSyncMeta(EMPTY_SYNC);
      setError("ZIP code and radius are required before searching inventory.");
      setLoading(false);
      return;
    }

    const params = new URLSearchParams();
    const makeModelPairs = buildMakeModelPairs(taxonomy, currentFilters);
    if (currentFilters.q.trim()) params.set("q", currentFilters.q.trim());
    if (currentFilters.make.length) params.set("make", currentFilters.make.join(","));
    if (currentFilters.model.length) params.set("model", currentFilters.model.join(","));
    if (makeModelPairs.length) params.set("make_model_pairs", makeModelPairs.join(","));
    if (currentFilters.trim.length) params.set("trim", currentFilters.trim.join(","));
    if (currentFilters.body_type.length) params.set("body_type", currentFilters.body_type.join(","));
    if (currentFilters.source_type.trim()) {
      params.set("source_type", normalizeSourceFilterValue(currentFilters.source_type));
    }
    if (currentFilters.state.trim()) params.set("state", currentFilters.state.trim().toUpperCase());

    if (currentFilters.zip_code.trim()) params.set("zip_code", currentFilters.zip_code.trim());
    if (currentFilters.radius.trim()) params.set("radius", currentFilters.radius.trim());
    if (currentFilters.min_price.trim()) params.set("min_price", currentFilters.min_price.trim());
    if (currentFilters.max_price.trim()) params.set("max_price", currentFilters.max_price.trim());
    if (currentFilters.min_year.trim()) params.set("min_year", currentFilters.min_year.trim());
    if (currentFilters.max_year.trim()) params.set("max_year", currentFilters.max_year.trim());
    if (currentFilters.min_miles.trim()) params.set("min_miles", currentFilters.min_miles.trim());
    if (currentFilters.max_miles.trim()) params.set("max_miles", currentFilters.max_miles.trim());
    if (currentFilters.exterior_color.length) params.set("exterior_color", currentFilters.exterior_color.join(","));
    if (currentFilters.interior_color.length) params.set("interior_color", currentFilters.interior_color.join(","));
    params.set("has_images", currentFilters.has_images ? "true" : "false");
    params.set("live_sync", currentFilters.live_sync ? "true" : "false");
    params.set("sync_limit", "72");
    params.set("sort_by", currentFilters.sort_by);
    params.set("sort_dir", currentFilters.sort_dir);
    params.set("page", String(currentPage));
    params.set("per_page", "18");

    const response = await apiFetch<InventorySearchPayload>(`/inventory/search?${params.toString()}`);
    if (!isCurrentRequest()) return;
    if (response.status !== "ok") {
      setRows([]);
      setPagination(EMPTY_PAGINATION);
      setSyncMeta(EMPTY_SYNC);
      setError(response.error?.message || "Failed to load inventory.");
      setLoading(false);
      return;
    }

    const items = response.data.items || [];
    const pag = response.data.pagination || EMPTY_PAGINATION;
    setRows(items);
    setPagination(pag);
    setSyncMeta(response.data.sync || EMPTY_SYNC);
    setLoading(false);

    // Cache results so back-navigation from VDP can restore without re-fetching
    try {
      window.sessionStorage.setItem(
        SEARCH_RESULTS_CACHE_KEY,
        JSON.stringify({ cached_at: Date.now(), items, pagination: pag, filters: currentFilters, page: currentPage }),
      );
    } catch { /* storage full or disabled */ }
  }

  async function loadAccountStatus(accessToken: string) {
    const response = await apiFetch<{ is_preapproved: boolean }>(
      "/me/account-status",
      {},
      accessToken,
    );
    if (response.status === "ok" && response.data) {
      setIsPreapproved(Boolean(response.data.is_preapproved));
    } else {
      setIsPreapproved(false);
    }
  }

  async function loadGarage(accessToken: string) {
    setGarageLoading(true);
    setGarageError(null);
    setGarageNotice(null);
    const response = await apiFetch<GarageItem[]>("/me/garage", {}, accessToken);
    if (handleUnauthorized(response)) {
      setGarageLoading(false);
      return;
    }
    if (response.status !== "ok") {
      setGarageItems([]);
      setGarageError(response.error?.message || "Unable to load garage.");
      setGarageLoading(false);
      return;
    }
    setGarageItems(response.data || []);
    setGarageLoading(false);
  }

  async function submitFilters(event: FormEvent) {
    event.preventDefault();

    const qVal = filters.q.trim();
    const isVinSubmit = qVal.length === 17 && /^[A-Za-z0-9]+$/.test(qVal);
    if (!isVinSubmit && (!filters.zip_code.trim() || !filters.radius.trim())) {
      setError("ZIP code and radius are required before searching inventory.");
      setOpenFilter(null);
      return;
    }
    const submittedFilters: FilterState = {
      ...filters,
      source_type: normalizeSourceFilterValue(filters.source_type),
    };
    setSearchMode("inventory");
    try {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.delete("hot_deals");
      window.history.replaceState(null, "", `${nextUrl.pathname}${nextUrl.search}`);
    } catch {
      // History updates are cosmetic; the submitted search still runs.
    }
    void loadFacets(submittedFilters);
    persistSearchContext(submittedFilters);
    setReadyToSearchMessage(null);
    setFiltersReady(true);
    setPage(1);
    setFilters(submittedFilters);
    setAppliedFilters({ ...submittedFilters });
    collapseMobileFilters();
    queueMobileResultsScroll();
  }

  function goToPage(nextPage: number | ((current: number) => number)) {
    setPage(nextPage);
    queueMobileResultsScroll();
  }

  function resetFilters() {
    try {
      window.sessionStorage.removeItem(SEARCH_FILTERS_KEY);
      window.localStorage.removeItem(SEARCH_CONTEXT_KEY);
      window.localStorage.removeItem(SEARCH_FILTERS_LOCAL_KEY);
      window.history.replaceState(null, "", window.location.pathname);
    } catch {
      // Browser storage/history can fail in private modes; state reset still works.
    }
    setFilters(INITIAL_FILTERS);
    setAppliedFilters(INITIAL_FILTERS);
    setSearchMode("hot_deals");
    setReadyToSearchMessage(null);
    setFiltersReady(true);
    setError(null);
    setPage(1);
  }

  async function openVehicleModal(vin: string) {
    setSelectedVin(vin);
    setDetailError(null);

    const cached = detailsByVin[vin];
    if (cached) {
      const cachedImages = resolveDisplayImages(cached);
      setSelectedImage(resolveHeroImage(cached) || cachedImages[0] || null);
      return;
    }

    setDetailLoading(true);
    const response = await apiFetch<VehicleDetail>(`/inventory/${encodeURIComponent(vin)}`);
    if (response.status !== "ok") {
      setDetailError(response.error?.message || "Unable to load vehicle details.");
      setDetailLoading(false);
      return;
    }

    setDetailsByVin((prev) => ({ ...prev, [vin]: response.data }));
    const nextImages = resolveDisplayImages(response.data);
    setSelectedImage(resolveHeroImage(response.data) || nextImages[0] || null);
    setDetailLoading(false);
  }

  function closeModal() {
    setSelectedVin(null);
    setDetailError(null);
    setDetailLoading(false);
    setSelectedImage(null);
  }

  function requireAuth(actionType: "garage" | "remove" | "acquire" | "cr", vin: string): AuthState | null {
    if (!auth?.accessToken) {
      setPendingActionType(actionType);
      setPendingActionVin(vin);
      setShowAuthModal(true);
      return null;
    }
    return auth;
  }

  async function addToGarage(vin: string, sessionOverride?: AuthState) {
    const session = sessionOverride || requireAuth("garage", vin);
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageNotice(null);
    const response = await apiFetch<{
      garage_item: GarageItem;
      ove_detail_refresh?: {
        queued?: boolean;
        deduplicated?: boolean;
      } | null;
      dealer_photos_fetched?: number;
    }>(`/me/garage/${encodeURIComponent(vin)}`, { method: "POST" }, session.accessToken);
    if (handleUnauthorized(response)) {
      setGarageActionVin(null);
      return;
    }
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to save vehicle to garage.");
      setGarageActionVin(null);
      return;
    }
    setGarageItems((prev) => {
      const remaining = prev.filter((item) => item.vin !== response.data.garage_item.vin);
      return [response.data.garage_item, ...remaining];
    });

    const photoCount = response.data.dealer_photos_fetched || 0;
    if (photoCount > 0) {
      setGarageNotice(`Vehicle saved. ${photoCount} dealer photos unlocked — view them in My Garage.`);
    } else if (response.data.ove_detail_refresh?.queued) {
      setGarageNotice(
        response.data.ove_detail_refresh.deduplicated
          ? "Inspection details are already being refreshed for this vehicle."
          : "Inspection details requested. Images and condition data will update when they are ready."
      );
    } else {
      setGarageNotice("Vehicle saved to My Garage.");
    }
    setGarageActionVin(null);
  }

  async function removeFromGarage(vin: string, sessionOverride?: AuthState) {
    const session = sessionOverride || requireAuth("remove", vin);
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageNotice(null);
    const response = await apiFetch<{ vin: string; status: string }>(
      `/me/garage/${encodeURIComponent(vin)}`,
      { method: "DELETE" },
      session.accessToken
    );
    if (handleUnauthorized(response)) {
      setGarageActionVin(null);
      return;
    }
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to remove vehicle from garage.");
      setGarageActionVin(null);
      return;
    }
    setGarageItems((prev) => prev.filter((item) => item.vin !== vin));
    setGarageActionVin(null);
  }

  async function startAcquisition(vin: string, sessionOverride?: AuthState) {
    const session = sessionOverride || requireAuth("acquire", vin);
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageNotice(null);
    const response = await apiFetch<{
      garage_item: GarageItem;
      deal: { id: string; stage: string; selected_vin: string };
      ove_detail_refresh?: {
        queued?: boolean;
        deduplicated?: boolean;
      } | null;
    }>(`/me/garage/${encodeURIComponent(vin)}/acquire`, { method: "POST" }, session.accessToken);
    if (handleUnauthorized(response)) {
      setGarageActionVin(null);
      return;
    }
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to start purchase.");
      setGarageActionVin(null);
      return;
    }

    setGarageItems((prev) => {
      const remaining = prev.filter((item) => item.vin !== response.data.garage_item.vin);
      return [response.data.garage_item, ...remaining];
    });
    setGarageNotice(
      response.data.ove_detail_refresh?.queued
        ? response.data.ove_detail_refresh.deduplicated
          ? "Purchase started. Inspection details are already being refreshed."
          : "Purchase started. Inspection details have been requested."
        : "Purchase started."
    );
    setGarageActionVin(null);
    window.location.href = `/dashboard?vin=${encodeURIComponent(vin)}`;
  }

  async function requestConditionReport(vin: string, sessionOverride?: AuthState) {
    const session = sessionOverride || requireAuth("cr", vin);
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageNotice(null);

    const response = await apiFetch<{
      queued?: boolean;
      deduplicated?: boolean;
      already_available?: boolean;
      message?: string;
    }>(`/me/vehicles/${encodeURIComponent(vin)}/condition-report-request`, { method: "POST" }, session.accessToken);

    if (handleUnauthorized(response)) {
      setGarageActionVin(null);
      return;
    }
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to request inspection report.");
      setGarageActionVin(null);
      return;
    }

    await loadGarage(session.accessToken);
    setGarageNotice(
      response.data.message ||
        (response.data.already_available
          ? "Inspection report is already available for this vehicle."
          : "Inspection report requested. We will update My Garage when it is ready.")
    );
    setGarageActionVin(null);
  }

  const pageButtons = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, pagination.page - 2);
    const end = Math.min(pagination.total_pages, pagination.page + 2);
    for (let value = start; value <= end; value += 1) pages.push(value);
    return pages;
  }, [pagination.page, pagination.total_pages]);

  const selectedVehicle = selectedVin ? detailsByVin[selectedVin] : null;
  const selectedVehicleImages = resolveDisplayImages(selectedVehicle);
  const selectedVehiclePrimaryImage = selectedImage || resolveHeroImage(selectedVehicle) || selectedVehicleImages[0] || null;
  const garageVins = useMemo(() => new Set(garageItems.map((item) => item.vin)), [garageItems]);
  const syncWarning = sanitizeSyncWarning(syncMeta.error);

  return (
    <>
      <div className="inventory-layout">
        <aside className={`card inventory-sidebar${filtersOpen ? " filters-open" : ""}`}>
          <button
            className="button ghost inventory-filter-toggle"
            type="button"
            onClick={() => setFiltersOpen((prev) => !prev)}
          >
            {filtersOpen ? "Hide Filters" : "Show Filters"}
          </button>
          <div className="inventory-sidebar-head">
            <h2>Filter Vehicles</h2>
          </div>

          <form onSubmit={submitFilters} className="inventory-filter-form">
            <div className="inventory-required-location">
              <div className="inventory-mini-grid">
                <label>
                  ZIP Code
                  <input
                    className="input"
                    inputMode="numeric"
                    maxLength={5}
                    placeholder="33028"
                    required
                    value={filters.zip_code}
                    onChange={(event) =>
                      updateFilters((prev) => ({
                        ...prev,
                        zip_code: event.target.value.replace(/\D/g, "").slice(0, 5),
                      }))
                    }
                  />
                </label>
                <label>
                  Radius
                  <select
                    className="select"
                    required
                    value={filters.radius}
                    onChange={(event) => updateFilters((prev) => ({ ...prev, radius: event.target.value }))}
                  >
                    {[25, 50, 75, 100, 150, 200, 250, 300, 400, 500].map((value) => (
                      <option key={value} value={String(value)}>
                        {value} miles
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="inventory-required-note">* Required</p>
            </div>

            <label className="inventory-search-field">
              Search
              <input
                className="input"
                placeholder="VIN, make, model, trim"
                value={filters.q}
                onChange={(event) => updateFilters((prev) => ({ ...prev, q: event.target.value }))}
              />
            </label>

            <FilterSection
              id="body_type"
              title="Body Type"
              selectedCount={filters.body_type.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Body Type"
                options={bodyTypeOptions}
                selected={filters.body_type}
                onChange={(next) => updateFilters((prev) => ({ ...prev, body_type: next }))}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="make"
              title="Make"
              selectedCount={filters.make.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Make"
                options={makeOptions}
                selected={filters.make}
                onChange={(next) => updateFilters((prev) => ({ ...prev, make: next, model: [], trim: [] }))}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="model"
              title="Model"
              selectedCount={filters.model.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Model"
                options={modelOptions}
                selected={filters.model}
                onChange={(next) => updateFilters((prev) => ({ ...prev, model: next, trim: [] }))}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="trim"
              title="Trim"
              selectedCount={filters.trim.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Trim"
                options={trimOptions}
                selected={filters.trim}
                onChange={(next) => updateFilters((prev) => ({ ...prev, trim: next }))}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="price"
              title="Price"
              selectedCount={[filters.min_price, filters.max_price].filter((value) => value.trim()).length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <div className="inventory-mini-grid">
                <label>
                  Min Price
                  <input
                    className="input"
                    type="number"
                    value={filters.min_price}
                    onChange={(event) => setFilters((prev) => ({ ...prev, min_price: event.target.value }))}
                  />
                </label>
                <label>
                  Max Price
                  <input
                    className="input"
                    type="number"
                    value={filters.max_price}
                    onChange={(event) => setFilters((prev) => ({ ...prev, max_price: event.target.value }))}
                  />
                </label>
              </div>
            </FilterSection>

            <FilterSection
              id="year"
              title="Year"
              selectedCount={[filters.min_year, filters.max_year].filter((value) => value.trim()).length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <div className="inventory-mini-grid">
                <label>
                  Min Year
                  <input
                    className="input"
                    type="number"
                    value={filters.min_year}
                    onChange={(event) => setFilters((prev) => ({ ...prev, min_year: event.target.value }))}
                  />
                </label>
                <label>
                  Max Year
                  <input
                    className="input"
                    type="number"
                    value={filters.max_year}
                    onChange={(event) => setFilters((prev) => ({ ...prev, max_year: event.target.value }))}
                  />
                </label>
              </div>
            </FilterSection>

            <FilterSection
              id="mileage"
              title="Mileage"
              selectedCount={[filters.min_miles, filters.max_miles].filter((value) => value.trim()).length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <div className="inventory-mini-grid">
                <label>
                  Min Miles
                  <input
                    className="input"
                    type="number"
                    value={filters.min_miles}
                    onChange={(event) => setFilters((prev) => ({ ...prev, min_miles: event.target.value }))}
                  />
                </label>
                <label>
                  Max Miles
                  <input
                    className="input"
                    type="number"
                    value={filters.max_miles}
                    onChange={(event) => setFilters((prev) => ({ ...prev, max_miles: event.target.value }))}
                  />
                </label>
              </div>
            </FilterSection>

            <FilterSection
              id="exterior_color"
              title="Exterior Color"
              selectedCount={filters.exterior_color.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Exterior Color"
                options={EXTERIOR_COLOR_OPTIONS.map((c) => ({ item: c }))}
                selected={filters.exterior_color}
                onChange={(next) => setFilters((prev) => ({ ...prev, exterior_color: next }))}
                maxVisible={EXTERIOR_COLOR_OPTIONS.length}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="interior_color"
              title="Interior Color"
              selectedCount={filters.interior_color.length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <MultiSelectList
                label="Interior Color"
                options={INTERIOR_COLOR_OPTIONS.map((c) => ({ item: c }))}
                selected={filters.interior_color}
                onChange={(next) => setFilters((prev) => ({ ...prev, interior_color: next }))}
                maxVisible={INTERIOR_COLOR_OPTIONS.length}
                showLabel={false}
              />
            </FilterSection>

            <FilterSection
              id="source"
              title="Source"
              selectedCount={filters.source_type ? 1 : 0}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <label>
                Source
                <select
                  className="select"
                  value={filters.source_type}
                  onChange={(event) => updateFilters((prev) => ({ ...prev, source_type: event.target.value }))}
                >
                  <option value="">Any</option>
                  <option value="auction">Wholesale Direct</option>
                  <option value="wholesale">Surplus Inventory</option>
                  <option value="dealer_partner">Partner Network</option>
                </select>
              </label>
            </FilterSection>

            <FilterSection id="sort" title="Sort" openId={openFilter} onToggle={toggleFilterSection}>
              <div className="inventory-mini-grid">
                <label>
                  Sort By
                  <select
                    className="select"
                    value={filters.sort_by}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, sort_by: event.target.value as FilterState["sort_by"] }))
                    }
                  >
                    <option value="updated_at">Recently Updated</option>
                    <option value="price_asking">Price</option>
                    <option value="year">Year</option>
                    <option value="odometer">Mileage</option>
                  </select>
                </label>
                <label>
                  Direction
                  <select
                    className="select"
                    value={filters.sort_dir}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, sort_dir: event.target.value as FilterState["sort_dir"] }))
                    }
                  >
                    <option value="desc">Descending</option>
                    <option value="asc">Ascending</option>
                  </select>
                </label>
              </div>
            </FilterSection>

            <FilterSection
              id="options"
              title="Options"
              selectedCount={[filters.has_images, filters.live_sync].filter(Boolean).length}
              openId={openFilter}
              onToggle={toggleFilterSection}
            >
              <label className="inventory-toggle">
                <input
                  type="checkbox"
                  checked={filters.has_images}
                  onChange={(event) => setFilters((prev) => ({ ...prev, has_images: event.target.checked }))}
                />
                Only show vehicles with photos
              </label>

              <label className="inventory-toggle">
                <input
                  type="checkbox"
                  checked={filters.live_sync}
                  onChange={(event) => setFilters((prev) => ({ ...prev, live_sync: event.target.checked }))}
                />
                Refresh current inventory on search
              </label>
            </FilterSection>

            <div className="inventory-actions">
              <button className="button" type="submit" disabled={loading}>
                {loading ? "Searching..." : "Search"}
              </button>
              <button className="button ghost" type="button" onClick={resetFilters} disabled={loading}>
                Reset
              </button>
            </div>
          </form>
        </aside>

        <section className="inventory-main" ref={resultsRef}>
          <header className="card inventory-results-header">
            <div>
              <h3 style={{ marginTop: 0, marginBottom: 6 }}>
                {searchMode === "hot_deals" ? "Hot Deals" : filtersReady ? "Vehicle Listings" : "Search Ready"}
              </h3>
              <p style={{ margin: 0 }}>
                {searchMode === "hot_deals"
                  ? "Danny's Picks from the current VHC Marketing List"
                  : !filtersReady
                    ? "Review the filters and click Search when you are ready."
                  : `${pagination.total.toLocaleString()} matches | Page ${pagination.page} of ${Math.max(pagination.total_pages, 1)}`}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span className="badge">Garage: {garageItems.length}</span>
              {syncMeta.requested ? (
                <span className="badge">
                  {syncWarning ? "Saved results" : syncMeta.executed ? "Inventory refreshed" : "Checking inventory"}
                </span>
              ) : (
                <span className="badge">Saved inventory</span>
              )}
              {auth?.accessToken ? (
                <>
                  <span className="badge">{auth.email || "buyer"}</span>
                  <button className="button ghost" onClick={() => loadGarage(auth.accessToken)} disabled={garageLoading}>
                    Refresh Garage
                  </button>
                  <button className="button ghost" onClick={signOut}>
                    Sign Out
                  </button>
                </>
              ) : (
                <Link className="button ghost" href="/dashboard">
                  Sign In for Garage
                </Link>
              )}
              <Link className="button ghost" href="/">
                Back Home
              </Link>
            </div>
          </header>

          {syncWarning && rows.length === 0 ? <div className="card">{syncWarning}</div> : null}
          {error ? <div className="card">{error}</div> : null}
          {!error && loading ? <SearchProgressOverlay /> : null}
          {!loading && !error && readyToSearchMessage ? (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>Validate Your Filters</h3>
              <p style={{ marginBottom: 0 }}>{readyToSearchMessage}</p>
            </div>
          ) : null}
          {!loading && !error && !readyToSearchMessage && rows.length === 0 ? (
            <div className="card">No vehicles match your current filters.</div>
          ) : null}

          {!loading && !error && rows.length > 0 ? (
            <div className="inventory-grid">
              {rows.map((item) => (
                <article className="card inventory-card" key={item.vin}>
                  <Link className="inventory-media-button" href={`/vinventory/${encodeURIComponent(publicIdentifier(item))}` as any}>
                    <div className="inventory-media" style={
                      !item.reference_pending && item.thumbnail && isChromeDataExterior(item.thumbnail)
                        ? { background: `url(${SHOWROOM_BG}) center bottom / cover no-repeat` }
                        : undefined
                    }>
                      {item.reference_pending ? (
                        <>
                          <img src={FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" style={{ opacity: 0.45 }} />
                          <div className="gated-photos-overlay" style={{ background: "rgba(0,0,0,0.55)" }}>
                            <span style={{ fontSize: "0.8rem" }}>Fetching Wholesale Images&hellip;</span>
                          </div>
                        </>
                      ) : item.thumbnail && isChromeDataExterior(item.thumbnail) ? (
                        <img
                          src={item.thumbnail}
                          alt={`${item.year} ${item.make} ${item.model}`}
                          loading="lazy"
                          style={{ objectFit: "contain", objectPosition: "center bottom", transform: "translateY(18%) scale(1.25)", transformOrigin: "center bottom" }}
                        />
                      ) : item.thumbnail ? (
                        <img src={item.thumbnail} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      ) : (
                        <img src={FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      )}
                      {item.hot_deal?.auction_end_at ? (
                        <span className="hot-deal-countdown">{formatHotDealCountdown(item.hot_deal.auction_end_at)}</span>
                      ) : null}
                      {!item.reference_pending && item.dealer_photos_gated && !garageVins.has(item.vin) ? (
                        <div className="gated-photos-overlay">
                          <span>More Images Available</span>
                        </div>
                      ) : null}
                    </div>
                  </Link>
                  <div className="inventory-card-body">
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <strong>
                        {item.year} {item.make} {item.model}
                      </strong>
                      <span className="badge">{toPublicSourceLabel(item.source_label, item.source_filter_value || item.source_type)}</span>
                    </div>
                    <p className="inventory-price">${item.price_asking.toLocaleString()}</p>
                    {item.badges && item.badges.length > 0 && (
                      <div className="inventory-badges" style={{ display: "flex", flexWrap: "wrap", gap: 4, margin: "4px 0" }}>
                        {item.badges.map((b) => (
                          <span key={b.type} className={`badge badge--${b.color}`} title={b.ratio ? `Price/MMR: ${b.ratio}` : undefined}>
                            {b.label}
                          </span>
                        ))}
                      </div>
                    )}
                    <p style={{ margin: 0 }}>
                      {item.trim || "Base"} | {item.drivetrain || "N/A"} | {item.exterior_color || "N/A"}
                    </p>
                    <p style={{ margin: 0, fontSize: 12, color: "var(--muted)" }}>
                      {[item.engine_type, item.transmission, item.fuel_type].filter(Boolean).join(" | ") || "Specs pending"}
                    </p>
                    <p style={{ margin: 0 }}>
                      {formatMiles(item.odometer)} {item.odometer_units || "mi"} | {item.location_state || "NA"} {item.location_zip || ""}
                    </p>
                    <p style={{ margin: 0 }}>VIN: {maskVin(item.vin, isAdminUser(auth) || (isPreapproved && garageVins.has(item.vin)))}</p>
                    <p className="inventory-description">
                      {item.features_preview?.length
                        ? item.features_preview.join(" • ")
                        : item.source_type === "ove" || item.source_type === "auction"
                          ? "Wholesale listing with live pricing. Inspection reports unlock as you get closer to buying."
                          : `${toPublicSourceLabel(item.source_label, item.source_filter_value || item.source_type)} listing with current specs and media.`}
                    </p>

                    <div className="inventory-actions inventory-card-actions">
                      <Link className="button" href={`/vinventory/${encodeURIComponent(publicIdentifier(item))}` as any}>
                        View Details
                      </Link>
                      <button className="button ghost inventory-quick-view-btn" onClick={() => openVehicleModal(item.vin)}>
                        <QuickViewIcon />
                        <span>Quick View</span>
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {pagination.total_pages > 1 ? (
            <section className="card inventory-pagination">
              <button
                className="button ghost"
                onClick={() => goToPage((prev) => Math.max(1, prev - 1))}
                disabled={!pagination.has_prev || loading}
              >
                Previous
              </button>
              {pageButtons.map((value) => (
                <button
                  key={value}
                  className={`button ${value === pagination.page ? "" : "ghost"}`}
                  onClick={() => goToPage(value)}
                  disabled={loading}
                >
                  {value}
                </button>
              ))}
              <button
                className="button ghost"
                onClick={() => goToPage((prev) => prev + 1)}
                disabled={!pagination.has_next || loading}
              >
                Next
              </button>
            </section>
          ) : null}

        </section>
      </div>

      {selectedVin ? (
        <div className="inventory-modal-overlay" onClick={closeModal}>
          <section
            className="card inventory-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="inventory-modal-header">
              <h3 style={{ margin: 0 }}>Vehicle Detail</h3>
              <button className="button ghost" onClick={closeModal}>
                Close
              </button>
            </header>

            {detailError ? <div className="card">{detailError}</div> : null}
            {!detailError && detailLoading ? <div className="card">Loading vehicle details...</div> : null}

            {!detailLoading && !detailError && selectedVehicle ? (
              <div className="inventory-modal-body">
                <section className="inventory-modal-main">
                  <div className="inventory-modal-image" style={showroomContainerStyle(selectedVehiclePrimaryImage || FALLBACK_IMAGE)}>
                      {selectedVehiclePrimaryImage ? (
                        <img
                          src={selectedVehiclePrimaryImage}
                          alt={`${selectedVehicle.year} ${selectedVehicle.make} ${selectedVehicle.model}`}
                          className={showroomImageClassName(selectedVehiclePrimaryImage)}
                          style={showroomImageStyle(selectedVehiclePrimaryImage)}
                        />
                      ) : (
                      <img
                        src={FALLBACK_IMAGE}
                        alt={`${selectedVehicle.year} ${selectedVehicle.make} ${selectedVehicle.model}`}
                      />
                      )}
                    </div>
                  {selectedVehicleImages.length > 1 ? (
                    <div className="inventory-thumbnails">
                      {selectedVehicleImages.map((image) => (
                        <button
                          key={image}
                          className={`inventory-thumb ${selectedVehiclePrimaryImage === image ? "active" : ""}`}
                          style={showroomContainerStyle(image)}
                          onClick={() => setSelectedImage(image)}
                        >
                          <img
                            src={image}
                            alt="Vehicle thumbnail"
                            loading="lazy"
                            className={showroomImageClassName(image)}
                            style={showroomImageStyle(image)}
                          />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </section>

                <section className="inventory-modal-info">
                  <h2 style={{ marginTop: 0, marginBottom: 8 }}>
                    {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
                  </h2>
                  <p style={{ marginTop: 0 }}>
                    {selectedVehicle.trim || "Base"} | {selectedVehicle.body_type || "Unknown"} |{" "}
                    {selectedVehicle.drivetrain || "N/A"}
                  </p>
                  <p className="inventory-price">${selectedVehicle.price_asking.toLocaleString()}</p>
                  {selectedVehicle.badges && selectedVehicle.badges.length > 0 && (
                    <div className="inventory-badges" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                      {selectedVehicle.badges.map((b) => (
                        <span key={b.type} className={`badge badge--${b.color}`} title={b.ratio ? `Price/MMR: ${b.ratio}` : undefined}>
                          {b.label}
                        </span>
                      ))}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                    <span className="badge">VIN {maskVin(selectedVehicle.vin, isAdminUser(auth) || (isPreapproved && garageVins.has(selectedVehicle.vin)))}</span>
                    <span className="badge">{toPublicSourceLabel(selectedVehicle.source_label, selectedVehicle.source_type)}</span>
                    <span className="badge">Condition: {selectedVehicle.condition_grade || "N/A"}</span>
                    <span className="badge">
                      {selectedVehicle.location_state || "NA"} {selectedVehicle.location_zip || ""}
                    </span>
                  </div>

                  <div className="vinv-detail-grid">
                    <ModalDetailRow label="Body Style" value={selectedVehicle.body_type} />
                    <ModalDetailRow label="Drivetrain" value={selectedVehicle.drivetrain} />
                    <ModalDetailRow label="Engine" value={selectedVehicle.engine_type} />
                    <ModalDetailRow label="Transmission" value={selectedVehicle.transmission} />
                    <ModalDetailRow label="Fuel Type" value={selectedVehicle.fuel_type} />
                    <ModalDetailRow label="Exterior Color" value={selectedVehicle.exterior_color} />
                    <ModalDetailRow label="Interior Color" value={selectedVehicle.interior_color} />
                    <ModalDetailRow label="Odometer" value={selectedVehicle.odometer != null ? `${formatMiles(selectedVehicle.odometer)} ${selectedVehicle.odometer_units || "mi"}` : null} />
                  </div>

                  {selectedVehicle.features_raw.length ? (
                    <div className="inventory-feature-grid">
                      {selectedVehicle.features_raw.slice(0, 20).map((feature) => (
                        <span className="badge" key={feature}>
                          {feature}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {selectedVehicle.display_context?.disclaimer ? (
                    <div style={{ display: "grid", gap: 8 }}>
                      {(selectedVehicle.display_context?.has_reference_stock ||
                        selectedVehicle.display_context?.inspection_images?.length) ? (
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          {selectedVehicle.display_context?.has_reference_stock ? (
                            <span className="badge">
                              Factory reference images {selectedVehicle.display_context?.reference_images?.length || 0}
                            </span>
                          ) : null}
                          {selectedVehicle.display_context?.spin_images?.length ? (
                            <span className="badge">360 frames {selectedVehicle.display_context.spin_images.length}</span>
                          ) : null}
                          {selectedVehicle.display_context?.inspection_images?.length ? (
                            <span className="badge">
                              Inspection photos {selectedVehicle.display_context.inspection_images.length}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      <p style={{ marginBottom: 0 }}>{selectedVehicle.display_context.disclaimer}</p>
                    </div>
                  ) : null}

                  <div className="inventory-actions">
                    <button
                      className="button"
                      onClick={() => addToGarage(selectedVehicle.vin)}
                      disabled={garageVins.has(selectedVehicle.vin) || garageActionVin === selectedVehicle.vin}
                    >
                      {garageActionVin === selectedVehicle.vin
                        ? "Saving..."
                        : garageVins.has(selectedVehicle.vin)
                          ? "In Garage"
                          : "Add to My Garage"}
                    </button>
                    {canAccessConditionReports(auth, { isPreapproved }) && (selectedVehicle.source_type === "ove" || selectedVehicle.source_type === "auction") && !selectedVehicle.has_inspection_report ? (
                      <button
                        className="button ghost"
                        onClick={() => requestConditionReport(selectedVehicle.vin)}
                        disabled={garageActionVin === selectedVehicle.vin}
                      >
                        {garageActionVin === selectedVehicle.vin ? "Requesting..." : "Request Inspection Report"}
                      </button>
                    ) : null}
                    {canAccessConditionReports(auth, { isPreapproved }) && selectedVehicle.has_inspection_report ? (
                      <Link
                        className="button ghost"
                        href={`/vinventory/${encodeURIComponent(publicIdentifier(selectedVehicle))}/condition-report` as any}
                      >
                        Open Report
                      </Link>
                    ) : null}
                    <button
                      className="button ghost"
                      onClick={() => startAcquisition(selectedVehicle.vin)}
                      disabled={garageActionVin === selectedVehicle.vin}
                    >
                      {garageActionVin === selectedVehicle.vin ? "Starting..." : "Start Purchase"}
                    </button>
                    <Link className="button ghost" href={`/vinventory/${encodeURIComponent(publicIdentifier(selectedVehicle))}` as any}>
                      Full Detail Page
                    </Link>
                    {selectedVehicle.source_url ? (
                      <a className="button ghost" href={selectedVehicle.source_url} target="_blank" rel="noreferrer">
                        Open Original Listing
                      </a>
                    ) : null}
                  </div>
                </section>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}

      {showAuthModal ? (
        <AuthModal
          onClose={() => { setShowAuthModal(false); setPendingActionType(null); setPendingActionVin(null); }}
          onAuthenticated={(nextAuth) => {
            setAuth(nextAuth);
            setShowAuthModal(false);
            const actionType = pendingActionType;
            const actionVin = pendingActionVin;
            setPendingActionType(null);
            setPendingActionVin(null);
            if (actionType && actionVin) {
              if (actionType === "garage") addToGarage(actionVin, nextAuth);
              else if (actionType === "remove") removeFromGarage(actionVin, nextAuth);
              else if (actionType === "acquire") startAcquisition(actionVin, nextAuth);
              else if (actionType === "cr") requestConditionReport(actionVin, nextAuth);
            }
          }}
        />
      ) : null}
    </>
  );
}

function resolveDisplayImages(vehicle: VehicleDetail | null | undefined): string[] {
  if (!vehicle) return [];
  const primary = vehicle.display_images || vehicle.display_context?.gallery_images || [];
  if (primary.length) return primary.filter(Boolean);
  return (vehicle.images || []).filter(Boolean);
}

function resolveHeroImage(vehicle: VehicleDetail | null | undefined): string | null {
  if (!vehicle) return null;
  return vehicle.hero_image || vehicle.display_context?.hero_image || null;
}

function garageItemTitle(item: GarageItem): string {
  const year = item.vehicle.year ?? "";
  const make = item.vehicle.make ?? "";
  const model = item.vehicle.model ?? "";
  const title = `${year} ${make} ${model}`.trim();
  return title || item.vin;
}

function garageItemLocation(item: GarageItem): string {
  return `${item.vehicle.location_state || "NA"} ${item.vehicle.location_zip || ""}`.trim();
}

function ModalDetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="vinv-detail-row">
      <span className="vinv-detail-label">{label}</span>
      <span className="vinv-detail-value">{value || "N/A"}</span>
    </div>
  );
}

function formatMiles(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return value.toLocaleString();
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toLocaleString()}`;
}

function formatHotDealCountdown(value: string | null | undefined): string {
  if (!value) return "Auction ending soon";
  const end = new Date(value).getTime();
  if (Number.isNaN(end)) return "Auction ending soon";
  const totalSeconds = Math.floor(Math.max(0, end - Date.now()) / 1000);
  if (totalSeconds <= 0) return "Expired";
  if (totalSeconds < 60) return "Ending now";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours < 1) return `Ends in ${minutes}m`;
  return `Ends in ${hours}h ${minutes}m`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString();
}
