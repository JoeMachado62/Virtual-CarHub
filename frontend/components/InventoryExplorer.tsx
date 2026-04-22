/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AuctionSnapshotCard } from "@/components/AuctionSnapshotCard";
import { AuthModal } from "@/components/AuthModal";
import { ConditionReportCard } from "@/components/ConditionReportCard";
import { apiFetch } from "@/lib/api";
import { AuthState, clearAuthState, isAdminUser, loadValidAuthState } from "@/lib/auth";
import { normalizeSourceFilterValue, toPublicSourceLabel } from "@/lib/sourceLabels";
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
  make: string;
  model: string;
  trim: string;
  body_type: string;
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
  exterior_color: string;
  interior_color: string;
  has_images: boolean;
  live_sync: boolean;
  sort_by: "updated_at" | "price_asking" | "year" | "odometer";
  sort_dir: "asc" | "desc";
};

const INITIAL_FILTERS: FilterState = {
  q: "",
  make: "",
  model: "",
  trim: "",
  body_type: "",
  source_type: "",
  state: "",
  zip_code: "",
  radius: "250",
  min_price: "",
  max_price: "",
  min_year: "",
  max_year: "",
  min_miles: "",
  max_miles: "",
  exterior_color: "",
  interior_color: "",
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
const SEARCH_CONTEXT_KEY = "vch:inventory:search-context";
const SEARCH_FILTERS_KEY = "vch:inventory:filters";
const LIVE_SYNC_FALLBACK_MESSAGE = "Live wholesale sync is temporarily unavailable. Showing saved inventory results.";

const PROGRESS_MESSAGES = [
  "Checking surplus inventory listings\u2026",
  "Contacting wholesale sources\u2026",
  "Scanning dealer networks\u2026",
  "Vetting inventory quality\u2026",
  "Verifying vehicle history\u2026",
  "Matching factory specifications\u2026",
  "Preparing color-matched images\u2026",
  "Validating pricing information\u2026",
  "Cross-referencing market data\u2026",
  "Finalizing listing details\u2026",
];

function SearchProgressOverlay() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev < PROGRESS_MESSAGES.length - 1 ? prev + 1 : prev));
    }, 2200);
    return () => clearInterval(interval);
  }, []);

  const pct = Math.min(((step + 1) / PROGRESS_MESSAGES.length) * 100, 95);

  return (
    <div className="card" style={{ textAlign: "center", padding: "3rem 2rem" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <svg width="48" height="48" viewBox="0 0 48 48" style={{ animation: "spin 1.2s linear infinite" }}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="var(--accent, #3b82f6)" strokeWidth="4" strokeDasharray="90 40" strokeLinecap="round" />
        </svg>
      </div>
      <h3 style={{ margin: "0 0 0.75rem", fontSize: "1.15rem" }}>Searching Wholesale Inventory</h3>
      <p style={{ margin: "0 0 1.5rem", opacity: 0.8, minHeight: "1.4em", transition: "opacity 0.3s" }}>
        {PROGRESS_MESSAGES[step]}
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

export function InventoryExplorer({ initialMake, initialModel, initialTrim }: InventoryExplorerProps = {}) {
  const searchParams = useSearchParams();
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingActionType, setPendingActionType] = useState<"garage" | "remove" | "acquire" | "cr" | null>(null);
  const [pendingActionVin, setPendingActionVin] = useState<string | null>(null);

  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [filtersReady, setFiltersReady] = useState(false);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<InventoryItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>(EMPTY_PAGINATION);
  const [syncMeta, setSyncMeta] = useState<SyncMeta>(EMPTY_SYNC);
  const [taxonomy, setTaxonomy] = useState<InventoryFacetPayload["taxonomy"] | null>(null);
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
  const [garageActionVin, setGarageActionVin] = useState<string | null>(null);
  const [garageError, setGarageError] = useState<string | null>(null);
  const [garageNotice, setGarageNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const saved = await loadValidAuthState();
      if (cancelled || !saved) return;
      setAuth(saved);
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // SEO route props take priority when no explicit URL search params are set
    if (initialMake && !searchParams.has("make")) {
      const nextFilters: FilterState = {
        ...INITIAL_FILTERS,
        make: initialMake,
        ...(initialModel ? { model: initialModel } : {}),
        ...(initialTrim ? { trim: initialTrim } : {}),
      };
      setFilters(nextFilters);
      setAppliedFilters(nextFilters);
      setFiltersReady(true);
      return;
    }

    // Check if URL has search params (from NLP, DealBuilder, etc.)
    const hasUrlParams = Array.from(searchParams.keys()).some(
      (k) => !["nlp_query"].includes(k) && searchParams.get(k),
    );

    if (hasUrlParams) {
      // ── URL params present: build filters from URL ──
      const vinParam = searchParams.get("vin") || "";
      const q = vinParam || searchParams.get("q") || "";
      const sourceType = normalizeSourceFilterValue(searchParams.get("source_type"));
      const make = searchParams.get("make") || "";
      const model = searchParams.get("model") || "";
      const trim = searchParams.get("trim") || "";
      const bodyType = searchParams.get("body_type") || "";
      const minYear = searchParams.get("min_year") || "";
      const maxYear = searchParams.get("max_year") || "";
      const minPrice = searchParams.get("min_price") || "";
      const maxPrice = searchParams.get("max_price") || "";
      const minMiles = searchParams.get("min_miles") || "";
      const maxMiles = searchParams.get("max_miles") || "";
      const exteriorColor = searchParams.get("exterior_color") || "";
      const interiorColor = searchParams.get("interior_color") || "";
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
      setFilters(nextFilters);
      setAppliedFilters(nextFilters);
      setFiltersReady(true);
      return;
    }

    // ── No URL params: restore from sessionStorage or localStorage ──
    try {
      const savedFilters = window.sessionStorage.getItem(SEARCH_FILTERS_KEY);
      if (savedFilters) {
        const restored = JSON.parse(savedFilters) as FilterState;
        const hasFilters = restored.make || restored.model || restored.q
          || restored.min_year || restored.max_year || restored.min_price
          || restored.max_price || restored.min_miles || restored.max_miles
          || restored.zip_code;
        if (hasFilters) {
          setFilters(restored);
          setAppliedFilters(restored);
          setFiltersReady(true);
          return;
        }
      }

      const raw = window.localStorage.getItem(SEARCH_CONTEXT_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<Pick<FilterState, "zip_code" | "radius">>;
        if (parsed.zip_code || parsed.radius) {
          setFilters((prev) => ({ ...prev, ...parsed }));
          setAppliedFilters((prev) => ({ ...prev, ...parsed }));
        }
      }
    } catch { /* ignore */ }

    setFiltersReady(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    void loadFacets(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.make, filters.model, filters.min_year, filters.max_year, filters.has_images]);

  useEffect(() => {
    if (!filtersReady) return;
    void loadInventory(appliedFilters, page);
  }, [filtersReady, appliedFilters, page]);

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
          radius: nextFilters.radius || "250",
        })
      );
      // Save full filter state to sessionStorage so it survives navigation
      window.sessionStorage.setItem(SEARCH_FILTERS_KEY, JSON.stringify(nextFilters));
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
    if (currentFilters.make.trim()) params.set("make", currentFilters.make.trim());
    if (currentFilters.model.trim()) params.set("model", currentFilters.model.trim());
    if (currentFilters.trim.trim()) params.set("trim", currentFilters.trim.trim());
    if (currentFilters.min_year.trim()) params.set("min_year", currentFilters.min_year.trim());
    if (currentFilters.max_year.trim()) params.set("max_year", currentFilters.max_year.trim());
    if (currentFilters.body_type.trim()) params.set("body_type", currentFilters.body_type.trim());
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
  }

  async function loadInventory(currentFilters: FilterState, currentPage: number) {
    setLoading(true);
    setError(null);

    // ZIP is optional for auction searches, VIN lookups, and specific make/model queries
    const isAuctionSearch = currentFilters.source_type === "auction";
    const isVinSearch = currentFilters.q.trim().length === 17 && /^[A-HJ-NPR-Z0-9]+$/i.test(currentFilters.q.trim());
    const hasStructuredFilters = Boolean(currentFilters.make.trim() || currentFilters.model.trim());

    if (!isAuctionSearch && !isVinSearch && !hasStructuredFilters && !currentFilters.zip_code.trim()) {
      setRows([]);
      setPagination(EMPTY_PAGINATION);
      setSyncMeta(EMPTY_SYNC);
      setError("Enter a ZIP code, VIN, or specify a make/model to search inventory.");
      setLoading(false);
      return;
    }

    const params = new URLSearchParams();
    if (currentFilters.q.trim()) params.set("q", currentFilters.q.trim());
    if (currentFilters.make.trim()) params.set("make", currentFilters.make.trim());
    if (currentFilters.model.trim()) params.set("model", currentFilters.model.trim());
    if (currentFilters.trim.trim()) params.set("trim", currentFilters.trim.trim());
    if (currentFilters.body_type.trim()) params.set("body_type", currentFilters.body_type.trim());
    if (currentFilters.source_type.trim()) {
      params.set("source_type", normalizeSourceFilterValue(currentFilters.source_type));
    }
    if (currentFilters.state.trim()) params.set("state", currentFilters.state.trim().toUpperCase());

    // Only add ZIP and radius for non-auction searches or if ZIP is provided
    if (currentFilters.zip_code.trim()) {
      params.set("zip_code", currentFilters.zip_code.trim());
      if (currentFilters.radius.trim()) params.set("radius", currentFilters.radius.trim());
    }
    if (currentFilters.min_price.trim()) params.set("min_price", currentFilters.min_price.trim());
    if (currentFilters.max_price.trim()) params.set("max_price", currentFilters.max_price.trim());
    if (currentFilters.min_year.trim()) params.set("min_year", currentFilters.min_year.trim());
    if (currentFilters.max_year.trim()) params.set("max_year", currentFilters.max_year.trim());
    if (currentFilters.min_miles.trim()) params.set("min_miles", currentFilters.min_miles.trim());
    if (currentFilters.max_miles.trim()) params.set("max_miles", currentFilters.max_miles.trim());
    if (currentFilters.exterior_color.trim()) params.set("exterior_color", currentFilters.exterior_color.trim());
    if (currentFilters.interior_color.trim()) params.set("interior_color", currentFilters.interior_color.trim());
    params.set("has_images", currentFilters.has_images ? "true" : "false");
    params.set("live_sync", currentFilters.live_sync ? "true" : "false");
    params.set("sync_limit", "72");
    params.set("sort_by", currentFilters.sort_by);
    params.set("sort_dir", currentFilters.sort_dir);
    params.set("page", String(currentPage));
    params.set("per_page", "18");

    const response = await apiFetch<InventorySearchPayload>(`/inventory/search?${params.toString()}`);
    if (response.status !== "ok") {
      setRows([]);
      setPagination(EMPTY_PAGINATION);
      setSyncMeta(EMPTY_SYNC);
      setError(response.error?.message || "Failed to load inventory.");
      setLoading(false);
      return;
    }

    setRows(response.data.items || []);
    setPagination(response.data.pagination || EMPTY_PAGINATION);
    setSyncMeta(response.data.sync || EMPTY_SYNC);
    setLoading(false);
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

    // For auction searches, ZIP code is optional
    const isAuctionSearch = filters.source_type === "auction";

    if (!isAuctionSearch && !filters.zip_code.trim()) {
      setError("ZIP code is required to search inventory (except for auction vehicles).");
      return;
    }
    await loadFacets(filters);
    persistSearchContext(filters);
    setPage(1);
    setAppliedFilters({ ...filters });
  }

  function resetFilters() {
    setFilters(INITIAL_FILTERS);
    setAppliedFilters(INITIAL_FILTERS);
    persistSearchContext(INITIAL_FILTERS);
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
          ? "Auction detail refresh was already queued for this vehicle."
          : "Auction detail refresh queued. Images and condition data will update when the scraper responds."
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
      setGarageError(response.error?.message || "Unable to start acquisition.");
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
          ? "Acquisition started. Auction detail refresh was already in progress."
          : "Acquisition started and auction detail refresh queued for the back office."
        : "Acquisition started."
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
      setGarageError(response.error?.message || "Unable to request condition report.");
      setGarageActionVin(null);
      return;
    }

    await loadGarage(session.accessToken);
    setGarageNotice(
      response.data.message ||
        (response.data.already_available
          ? "Condition report is already available for this vehicle."
          : "Condition report requested. The back office scraper queue has been updated.")
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
            <label>
              Search
              <input
                className="input"
                placeholder="VIN, make, model, trim"
                value={filters.q}
                onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
              />
            </label>

            <div className="inventory-mini-grid">
              <label>
                Make
                <select
                  className="select"
                  value={filters.make}
                  onChange={(event) =>
                    updateFilters((prev) => ({
                      ...prev,
                      make: event.target.value,
                      model: "",
                      trim: "",
                    }))
                  }
                >
                  <option value="">Any Make</option>
                  {(taxonomy?.make || []).map((bucket) => (
                    <option key={bucket.item} value={bucket.item}>
                      {bucket.item}
                      {bucket.count ? ` (${bucket.count.toLocaleString()})` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Model
                <select
                  className="select"
                  value={filters.model}
                  onChange={(event) =>
                    updateFilters((prev) => ({
                      ...prev,
                      model: event.target.value,
                      trim: "",
                    }))
                  }
                  disabled={!filters.make}
                >
                  <option value="">{filters.make ? "Select Model" : "Choose Make First"}</option>
                  {(taxonomy?.model || []).map((bucket) => (
                    <option key={bucket.item} value={bucket.item}>
                      {bucket.item}
                      {bucket.count ? ` (${bucket.count.toLocaleString()})` : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                Trim
                <select
                  className="select"
                  value={filters.trim}
                  onChange={(event) => updateFilters((prev) => ({ ...prev, trim: event.target.value }))}
                  disabled={!filters.make || !filters.model}
                >
                  <option value="">{filters.model ? "Any Trim" : "Choose Model First"}</option>
                  {(taxonomy?.trim || []).map((bucket) => (
                    <option key={bucket.item} value={bucket.item}>
                      {bucket.item}
                      {bucket.count ? ` (${bucket.count.toLocaleString()})` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Body Type
                <input
                  className="input"
                  placeholder="SUV, Truck, Sed"
                  value={filters.body_type}
                  onChange={(event) => setFilters((prev) => ({ ...prev, body_type: event.target.value }))}
                />
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                ZIP Code
                <input
                  className="input"
                  inputMode="numeric"
                  maxLength={5}
                  placeholder="33028"
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
                  value={filters.radius}
                  onChange={(event) => updateFilters((prev) => ({ ...prev, radius: event.target.value }))}
                >
                  {[25, 50, 75, 100, 150, 200, 250].map((value) => (
                    <option key={value} value={String(value)}>
                      {value} miles
                    </option>
                  ))}
                </select>
              </label>
            </div>

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

            <div className="inventory-mini-grid">
              <label>
                Exterior Color
                <select
                  className="select"
                  value={filters.exterior_color}
                  onChange={(event) => setFilters((prev) => ({ ...prev, exterior_color: event.target.value }))}
                >
                  <option value="">Chose Color</option>
                  {EXTERIOR_COLOR_OPTIONS.map((color) => (
                    <option key={color} value={color}>{color}</option>
                  ))}
                </select>
              </label>
              <label>
                Interior Color
                <select
                  className="select"
                  value={filters.interior_color}
                  onChange={(event) => setFilters((prev) => ({ ...prev, interior_color: event.target.value }))}
                >
                  <option value="">Chose Color</option>
                  {INTERIOR_COLOR_OPTIONS.map((color) => (
                    <option key={color} value={color}>{color}</option>
                  ))}
                </select>
              </label>
            </div>

            <label>
              Source
              <select
                className="select"
                value={filters.source_type}
                onChange={(event) => setFilters((prev) => ({ ...prev, source_type: event.target.value }))}
              >
                <option value="">Any</option>
                <option value="auction">Wholesale Direct</option>
                <option value="wholesale">Surplus Inventory</option>
                <option value="dealer_partner">Partner Network</option>
              </select>
            </label>

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
              Trigger live wholesale sync on search
            </label>

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

        <section className="inventory-main">
          <header className="card inventory-results-header">
            <div>
              <h3 style={{ marginTop: 0, marginBottom: 6 }}>Vehicle Listings</h3>
              <p style={{ margin: 0 }}>
                {pagination.total.toLocaleString()} matches | Page {pagination.page} of{" "}
                {Math.max(pagination.total_pages, 1)}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span className="badge">Garage: {garageItems.length}</span>
              {syncMeta.requested ? (
                <span className="badge">
                  {syncWarning ? "Local DB fallback" : `Sync ${syncMeta.executed ? syncMeta.mode : "pending"}`} | +
                  {syncMeta.inserted} new / {syncMeta.updated} upd
                </span>
              ) : (
                <span className="badge">Local DB search</span>
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
          {!loading && !error && rows.length === 0 ? (
            <div className="card">No vehicles match your current filters.</div>
          ) : null}

          {!loading && !error && rows.length > 0 ? (
            <div className="inventory-grid">
              {rows.map((item) => (
                <article className="card inventory-card" key={item.vin}>
                  <Link className="inventory-media-button" href={`/vinventory/${encodeURIComponent(publicIdentifier(item))}` as any}>
                    <div className="inventory-media">
                      {item.reference_pending ? (
                        <>
                          <img src={FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" style={{ opacity: 0.45 }} />
                          <div className="gated-photos-overlay" style={{ background: "rgba(0,0,0,0.55)" }}>
                            <span style={{ fontSize: "0.8rem" }}>Fetching Wholesale Images&hellip;</span>
                          </div>
                        </>
                      ) : item.thumbnail ? (
                        <img src={item.thumbnail} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      ) : (
                        <img src={FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      )}
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
                          ? "Auction listing with live pricing. Condition reports unlock as the buyer workflow advances."
                          : `${toPublicSourceLabel(item.source_label, item.source_filter_value || item.source_type)} listing with synced specs and media.`}
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
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={!pagination.has_prev || loading}
              >
                Previous
              </button>
              {pageButtons.map((value) => (
                <button
                  key={value}
                  className={`button ${value === pagination.page ? "" : "ghost"}`}
                  onClick={() => setPage(value)}
                  disabled={loading}
                >
                  {value}
                </button>
              ))}
              <button
                className="button ghost"
                onClick={() => setPage((prev) => prev + 1)}
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
                  <div className="inventory-modal-image">
                      {selectedVehiclePrimaryImage ? (
                        <img
                          src={selectedVehiclePrimaryImage}
                          alt={`${selectedVehicle.year} ${selectedVehicle.make} ${selectedVehicle.model}`}
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
                          onClick={() => setSelectedImage(image)}
                        >
                          <img src={image} alt="Vehicle thumbnail" loading="lazy" />
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

                  {selectedVehicle.source_type === "ove" || selectedVehicle.source_type === "auction" ? (
                    <>
                      <ConditionReportCard
                        report={selectedVehicle.condition_report}
                        grade={selectedVehicle.condition_report_grade || selectedVehicle.condition_grade}
                        sellerComments={selectedVehicle.seller_comments}
                        pickupLocation={selectedVehicle.pickup_location}
                        inventoryStatus={selectedVehicle.inventory_status || selectedVehicle.inventory_label}
                        mmr={selectedVehicle.mmr}
                        title="Auction Condition Summary"
                      />
                      <AuctionSnapshotCard snapshot={selectedVehicle.listing_snapshot} />
                    </>
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
                    {isAdminUser(auth) && (selectedVehicle.source_type === "ove" || selectedVehicle.source_type === "auction") && !selectedVehicle.has_inspection_report ? (
                      <button
                        className="button ghost"
                        onClick={() => requestConditionReport(selectedVehicle.vin)}
                        disabled={garageActionVin === selectedVehicle.vin}
                      >
                        {garageActionVin === selectedVehicle.vin ? "Requesting..." : "Request Condition Report"}
                      </button>
                    ) : null}
                    {isAdminUser(auth) && selectedVehicle.has_inspection_report ? (
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
                      {garageActionVin === selectedVehicle.vin ? "Starting..." : "Start Acquisition"}
                    </button>
                    <Link className="button ghost" href={`/vinventory/${encodeURIComponent(publicIdentifier(selectedVehicle))}` as any}>
                      Full Detail Page
                    </Link>
                    {selectedVehicle.source_url ? (
                      <a className="button ghost" href={selectedVehicle.source_url} target="_blank" rel="noreferrer">
                        Open Source Listing
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

function formatDate(value: string | null | undefined): string {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString();
}
