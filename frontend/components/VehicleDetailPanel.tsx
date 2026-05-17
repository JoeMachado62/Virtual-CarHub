/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import type { TouchEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { AuthModal } from "@/components/AuthModal";
import { apiFetch } from "@/lib/api";
import { AuthState, clearAuthState, isAdminUser, loadValidAuthState } from "@/lib/auth";
import { normalizeSourceFilterValue, toPublicSourceLabel } from "@/lib/sourceLabels";
import { maskVin } from "@/lib/vin";
import {
  CREDIT_TIER_DEFINITIONS,
  DEFAULT_CREDIT_TIER,
  DEFAULT_LOAN_TERM_MONTHS,
  type CreditTierId,
  buildVehiclePriceBreakdown,
  estimateMonthlyPayment,
  getCreditTierDefinition,
} from "@/lib/vehicleFinance";

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
  reference_color_exact?: boolean;
  imagin_images?: string[];
  spin_images?: string[];
  source_images?: string[];
  inspection_images?: string[];
  disclosure_images?: string[];
  evox_exterior_stills?: string[];
  evox_interior_stills?: string[];
  evox_spin_images?: string[];
  evox_interior_pano?: string[];
  has_evox_stock?: boolean;
  evox_color_exact?: boolean;
  has_inspection_report?: boolean;
  has_imagin_stock?: boolean;
  dealer_photos_gated?: boolean;
  gated_photo_count?: number;
  protected_photo_access?: boolean;
  disclaimer?: string;
  condition_report?: Record<string, unknown>;
};

type NhtsaCategoryItem = { icon: string; text: string };

type NhtsaDecoded = {
  specs?: NhtsaCategoryItem[];
  safety?: NhtsaCategoryItem[];
  build?: NhtsaCategoryItem[];
  highlights?: NhtsaCategoryItem[];
  exterior?: NhtsaCategoryItem[];
  interior?: NhtsaCategoryItem[];
  technology?: NhtsaCategoryItem[];
  engine_description?: string | null;
  transmission_description?: string | null;
  drive_type?: string | null;
  body_class?: string | null;
  fuel_type?: string | null;
  doors?: number | null;
  horsepower?: string | null;
};

type StructuredFeatureDetail = {
  category?: string | null;
  description: string;
  type?: string | null;
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
  source_price?: number | null;
  buy_fee?: number | null;
  margin?: number | null;
  price_wholesale_est?: number | null;
  location_zip?: string | null;
  location_state?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  description?: string | null;
  images: string[];
  display_images?: string[];
  photo_links?: string[];
  photo_links_cached?: string[];
  supplemental_photo_links?: string[];
  hero_image?: string | null;
  display_mode?: DisplayMode;
  inspection_status?: InspectionStatus;
  has_inspection_report?: boolean;
  can_view_protected_photos?: boolean;
  protected_photo_access_message?: string | null;
  display_context?: VehicleDisplayContext;
  source_label?: string | null;
  dealer_name?: string | null;
  city?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  transmission?: string | null;
  transmission_type?: string | null;
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
  mmr?: number | null;
  badges?: { type: string; label: string; color: string; ratio?: string }[];
  hot_deal?: {
    deal_label: string;
    deal_delta: number;
    mmr_value: number;
    auction_end_at: string;
    marketing_title?: string | null;
    marketing_summary?: string | null;
  } | null;
  features_raw: string[];
  high_value_features?: string[];
  options?: string[];
  option_packages?: string[];
  feature_details?: StructuredFeatureDetail[];
  high_value_feature_details?: StructuredFeatureDetail[];
  option_details?: StructuredFeatureDetail[];
  option_package_details?: StructuredFeatureDetail[];
  features_normalized: Record<string, unknown>;
  available: boolean;
  last_seen_active?: string | null;
  updated_at?: string | null;
  is_in_garage?: boolean;
  nhtsa_decoded?: NhtsaDecoded | null;
};

type SimilarVehicle = {
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  price_asking: number;
  odometer?: number | null;
  location_state?: string | null;
  location_zip?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  hero_image?: string | null;
};

type MarketComparisonPoint = {
  vin?: string | null;
  label: string;
  price: number;
  miles: number;
  source?: string | null;
  is_vch_listing?: boolean;
  href?: string | null;
};

type MarketComparisonData = {
  vin: string;
  generated_at?: string | null;
  this_vehicle: MarketComparisonPoint;
  comparables: MarketComparisonPoint[];
  national_average?: MarketComparisonPoint | null;
  metrics: {
    available_units?: number | null;
    market_days_supply?: number | null;
    sold_units_45_days?: number | null;
  };
  sources?: {
    local_comparable_count?: number;
    marketcheck_enabled?: boolean;
    marketcheck_comparable_count?: number;
    mds_available?: boolean;
    price_prediction_available?: boolean;
  };
};

const FALLBACK_IMAGE = "/assets/images/portfolio/VCH Auction default image.webp";
const SHOWROOM_BG = "/assets/images/portfolio/vch-showroom.webp";

const _EXTERIOR_SHOT_CODES = new Set(["01", "02", "03", "05", "06", "07"]);

function _extractShotCode(url: string): string | null {
  const match = url.match(/_(\d{2})\.\w{3,4}$/);
  return match ? match[1] : null;
}

function isChromeDataExterior(url: string | null | undefined): boolean {
  if (!url || !url.includes("media.chromedata.com")) return false;
  const shot = _extractShotCode(url);
  return !shot || _EXTERIOR_SHOT_CODES.has(shot);
}

function isSideProfile(url: string | null | undefined): boolean {
  if (!url) return false;
  return _extractShotCode(url) === "03";
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
    objectFit: "contain" as const,
    objectPosition: "center bottom",
    transformOrigin: "center bottom",
  };
}

function showroomImageClassName(url: string | null | undefined): string | undefined {
  if (!isChromeDataExterior(url)) return undefined;
  return isSideProfile(url) ? "vdp-showroom-image vdp-showroom-image-side" : "vdp-showroom-image";
}

const SEARCH_FILTERS_KEY = "vch:inventory:filters";

type InventorySearchItem = {
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  price_asking: number;
  odometer?: number | null;
  location_state?: string | null;
  location_zip?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  thumbnail?: string | null;
};

type InventorySearchPayload = {
  items: InventorySearchItem[];
};

type StoredSearchFilters = {
  q?: string;
  make?: string;
  model?: string;
  trim?: string;
  body_type?: string;
  source_type?: string;
  state?: string;
  zip_code?: string;
  radius?: string;
  min_price?: string;
  max_price?: string;
  min_year?: string;
  max_year?: string;
  min_miles?: string;
  max_miles?: string;
  exterior_color?: string;
  interior_color?: string;
  has_images?: boolean;
  sort_by?: "updated_at" | "price_asking" | "year" | "odometer";
  sort_dir?: "asc" | "desc";
};

/* ─── SVG Icon Components ─── */
function IconSpecs() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4m2-3v6m2-6h4"/>
    </svg>
  );
}
function IconHighlights() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
    </svg>
  );
}
function IconSafety() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  );
}
function IconExterior() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 17h14M5 17a2 2 0 01-2-2V9a2 2 0 012-2h2l2-3h6l2 3h2a2 2 0 012 2v6a2 2 0 01-2 2"/>
      <circle cx="7.5" cy="17" r="2.5"/><circle cx="16.5" cy="17" r="2.5"/>
    </svg>
  );
}
function IconInterior() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}
function IconTechnology() {
  return (
    <svg className="vdp-card-header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a10 10 0 0110 10 10 10 0 01-10 10A10 10 0 012 12 10 10 0 0112 2z"/>
      <path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z"/>
    </svg>
  );
}

/* Small inline item icon */
function ItemIcon() {
  return (
    <svg className="vdp-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
    </svg>
  );
}

/* ─── Category Card ─── */
function CategoryCard({ title, icon, items, color }: {
  title: string;
  icon: React.ReactNode;
  items: NhtsaCategoryItem[];
  color: string;
}) {
  const renderedItems = items.length ? items : [{ icon: "pending", text: "Details are being prepared." }];
  return (
    <div className="vdp-cat-card">
      <div className="vdp-cat-header" style={{ color }}>
        {icon}
        <h4>{title}</h4>
      </div>
      <ul className="vdp-cat-items">
        {renderedItems.map((item, i) => (
          <li key={i}><ItemIcon /><span>{item.text}</span></li>
        ))}
      </ul>
    </div>
  );
}

function IconTrend() {
  return (
    <svg className="vdp-market-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 17l5-5 4 4 7-8" />
      <path d="M15 8h5v5" />
      <circle cx="4" cy="17" r="1.6" />
      <circle cx="9" cy="12" r="1.6" />
      <circle cx="13" cy="16" r="1.6" />
    </svg>
  );
}

function IconVehicleMetric() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 16h14l-1.6-5.2A3 3 0 0014.5 8h-5a3 3 0 00-2.9 2.8L5 16z" />
      <path d="M7 16v2M17 16v2M7.5 18.5h0M16.5 18.5h0" />
      <path d="M8 12h8" />
    </svg>
  );
}

function IconCalendarMetric() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16" />
      <path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" />
    </svg>
  );
}

function IconSalesMetric() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19V9M10 19V5M16 19v-7M21 6l-5 5-4-4-7 7" />
      <path d="M18 6h3v3" />
    </svg>
  );
}

function niceStep(rawStep: number): number {
  if (!Number.isFinite(rawStep) || rawStep <= 0) return 1;
  const power = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const normalized = rawStep / power;
  if (normalized <= 1) return power;
  if (normalized <= 2) return 2 * power;
  if (normalized <= 5) return 5 * power;
  return 10 * power;
}

function buildTicks(min: number, max: number, count: number): number[] {
  const step = niceStep((max - min) / Math.max(1, count - 1));
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= end + step * 0.5; value += step) {
    ticks.push(value);
  }
  return ticks.slice(0, 8);
}

function formatCompactCurrency(value: number): string {
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}k`;
  return formatCurrency(value);
}

function formatCompactMiles(value: number): string {
  return Math.abs(value) >= 1000 ? `${Math.round(value / 1000)}k` : value.toLocaleString();
}

function MarketMetricCard({ icon, value, label, sublabel, highlight = false }: {
  icon: React.ReactNode;
  value: number | null | undefined;
  label: string;
  sublabel?: string;
  highlight?: boolean;
}) {
  return (
    <article className={`vdp-market-metric${highlight ? " highlight" : ""}`}>
      <span className="vdp-market-metric-icon">{icon}</span>
      <div>
        <strong>{value == null ? "N/A" : value.toLocaleString()}</strong>
        <span>{label}</span>
        {sublabel ? <em>{sublabel}</em> : null}
      </div>
    </article>
  );
}

function ValueComparisonDemandCard({ data, loading }: { data: MarketComparisonData | null; loading: boolean }) {
  if (loading && !data) {
    return (
      <section className="card vdp-market-card vdp-market-loading">
        <div className="vdp-market-heading">
          <span className="vdp-market-title-badge"><IconTrend /></span>
          <h2>Value Comparison &amp; Demand</h2>
        </div>
        <p>Loading market comparison...</p>
      </section>
    );
  }

  if (!data || !data.this_vehicle?.price || !data.this_vehicle?.miles) return null;

  const comparablePoints = (data.comparables || []).filter((point) => point.price > 0 && point.miles >= 0);
  const nationalPoint = data.national_average?.price && data.national_average?.miles != null
    ? data.national_average
    : null;
  const allPoints = [data.this_vehicle, ...comparablePoints, ...(nationalPoint ? [nationalPoint] : [])];
  const milesValues = allPoints.map((point) => point.miles);
  const priceValues = allPoints.map((point) => point.price);
  const minMiles = Math.min(...milesValues);
  const maxMiles = Math.max(...milesValues);
  const minPrice = Math.min(...priceValues);
  const maxPrice = Math.max(...priceValues);
  const milesPadding = Math.max((maxMiles - minMiles) * 0.12, 5000);
  const pricePadding = Math.max((maxPrice - minPrice) * 0.16, 1500);
  const xMin = Math.max(0, minMiles - milesPadding);
  const xMax = maxMiles + milesPadding;
  const yMin = Math.max(0, minPrice - pricePadding);
  const yMax = maxPrice + pricePadding;
  const xTicks = buildTicks(xMin, xMax, 6);
  const yTicks = buildTicks(yMin, yMax, 6);
  const width = 760;
  const height = 430;
  const pad = { top: 28, right: 22, bottom: 58, left: 74 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const xScale = (miles: number) => pad.left + ((miles - xMin) / Math.max(1, xMax - xMin)) * plotWidth;
  const yScale = (price: number) => pad.top + (1 - ((price - yMin) / Math.max(1, yMax - yMin))) * plotHeight;
  const similarLabel = comparablePoints.length ? `${comparablePoints.length} Similar Cars` : "Similar Cars";

  return (
    <section className="card vdp-market-card">
      <div className="vdp-market-heading">
        <span className="vdp-market-title-badge"><IconTrend /></span>
        <h2>Value Comparison &amp; Demand</h2>
      </div>

      <div className="vdp-market-layout">
        <div className="vdp-market-chart-panel">
          <div className="vdp-market-legend" aria-hidden="true">
            {nationalPoint ? <span><i className="national" /> {nationalPoint.label || "National Market Value"}</span> : null}
            <span><i className="similar" /> {similarLabel}</span>
            <span><i className="current" /> This Car</span>
          </div>

          <svg className="vdp-market-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Price and mileage comparison chart">
            {xTicks.map((tick) => (
              <g key={`x-${tick}`}>
                <line className="vdp-market-grid-line" x1={xScale(tick)} x2={xScale(tick)} y1={pad.top} y2={height - pad.bottom} />
                <text className="vdp-market-axis-text" x={xScale(tick)} y={height - 25} textAnchor="middle">{formatCompactMiles(tick)}</text>
              </g>
            ))}
            {yTicks.map((tick) => (
              <g key={`y-${tick}`}>
                <line className="vdp-market-grid-line" x1={pad.left} x2={width - pad.right} y1={yScale(tick)} y2={yScale(tick)} />
                <text className="vdp-market-axis-text" x={pad.left - 14} y={yScale(tick) + 5} textAnchor="end">{formatCompactCurrency(tick)}</text>
              </g>
            ))}
            <line className="vdp-market-axis-line" x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} />
            <line className="vdp-market-axis-line" x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} />
            <text className="vdp-market-axis-label" x={pad.left + plotWidth / 2} y={height - 5} textAnchor="middle">Miles</text>
            <text className="vdp-market-axis-label" transform={`translate(20 ${pad.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Price</text>

            {comparablePoints.map((point, index) => {
              const cx = xScale(point.miles);
              const cy = yScale(point.price);
              const title = `${point.label}: ${formatCurrency(point.price)}, ${point.miles.toLocaleString()} miles`;
              const dot = (
                <>
                  <title>{point.is_vch_listing ? `${title}. Opens this VirtualCarHub listing.` : title}</title>
                  <circle className={`vdp-market-dot similar${point.is_vch_listing ? " owned" : ""}`} cx={cx} cy={cy} r={point.is_vch_listing ? 7.5 : 6.2} />
                </>
              );
              return point.href ? (
                <a key={`${point.vin || "comp"}-${index}`} href={point.href} target="_blank" rel="noreferrer" aria-label={`Open ${point.label}`}>
                  {dot}
                </a>
              ) : (
                <g key={`${point.vin || "comp"}-${index}`}>{dot}</g>
              );
            })}

            {nationalPoint ? (
              <g>
                <title>{`${nationalPoint.label}: ${formatCurrency(nationalPoint.price)}, ${nationalPoint.miles.toLocaleString()} miles`}</title>
                <circle className="vdp-market-dot national" cx={xScale(nationalPoint.miles)} cy={yScale(nationalPoint.price)} r="9" />
              </g>
            ) : null}

            <g>
              <title>{`This car: ${formatCurrency(data.this_vehicle.price)}, ${data.this_vehicle.miles.toLocaleString()} miles`}</title>
              <circle className="vdp-market-dot current" cx={xScale(data.this_vehicle.miles)} cy={yScale(data.this_vehicle.price)} r="9" />
            </g>
          </svg>
        </div>

        <aside className="vdp-market-metrics">
          <MarketMetricCard icon={<IconVehicleMetric />} value={data.metrics.available_units} label="Available Units" />
          <MarketMetricCard icon={<IconCalendarMetric />} value={data.metrics.market_days_supply} label="Market Days" sublabel="Supply" />
          <MarketMetricCard icon={<IconSalesMetric />} value={data.metrics.sold_units_45_days} label="Sold Units" sublabel="past 45 days" highlight />
        </aside>
      </div>
    </section>
  );
}

export function VehicleDetailPanel({ vin }: { vin: string }) {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<"garage" | "acquire" | "cr" | null>(null);
  const [isPreapproved, setIsPreapproved] = useState(false);
  const [inGarage, setInGarage] = useState(false);
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [similar, setSimilar] = useState<SimilarVehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reportStatus, setReportStatus] = useState<"none" | "pending" | "available">("none");
  const [showAllFeatures, setShowAllFeatures] = useState(false);
  const [galleryIndex, setGalleryIndex] = useState(0);
  const [photoModalIndex, setPhotoModalIndex] = useState<number | null>(null);
  const [showPriceModal, setShowPriceModal] = useState(false);
  const [selectedCreditTier, setSelectedCreditTier] = useState<CreditTierId>(DEFAULT_CREDIT_TIER);
  const [downPaymentInput, setDownPaymentInput] = useState("");
  const [marketComparison, setMarketComparison] = useState<MarketComparisonData | null>(null);
  const [marketComparisonLoading, setMarketComparisonLoading] = useState(false);
  const [countdownNow, setCountdownNow] = useState(() => Date.now());
  const photoTouchStartX = useRef<number | null>(null);
  const topResetVin = useRef<string | null>(null);

  useEffect(() => {
    topResetVin.current = null;
    if (typeof window === "undefined") return;
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [vin]);

  useEffect(() => {
    const timer = window.setInterval(() => setCountdownNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      const saved = await loadValidAuthState();
      if (cancelled) return;
      setAuth(saved);
    }
    void restoreSession();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!auth?.accessToken) {
      setIsPreapproved(false);
      setInGarage(false);
      return;
    }
    async function loadAccessContext(accessToken: string) {
      const [statusRes, garageRes] = await Promise.all([
        apiFetch<{ is_preapproved: boolean }>("/me/account-status", {}, accessToken),
        apiFetch<Array<{ vin: string }>>("/me/garage", {}, accessToken),
      ]);
      if (cancelled) return;
      setIsPreapproved(statusRes.status === "ok" ? Boolean(statusRes.data?.is_preapproved) : false);
      if (garageRes.status === "ok" && Array.isArray(garageRes.data)) {
        const vinSet = new Set(garageRes.data.map((item) => item.vin));
        setInGarage(vinSet.has(vin));
      } else {
        setInGarage(false);
      }
    }
    void loadAccessContext(auth.accessToken);
    return () => { cancelled = true; };
  }, [auth?.accessToken, vin]);

  function handleUnauthorized(response: { error: { code: string; message: string } | null }): boolean {
    if (response.error?.code !== "HTTP_401") return false;
    clearAuthState();
    setAuth(null);
    setActionError("Your session expired. Sign in again from VInventory.");
    setActionMessage(null);
    return true;
  }

  async function loadSimilarListings(currentVehicle: VehicleDetail) {
    const storedFilters = readStoredSearchFilters();
    const searchParams = buildStoredSearchParams(storedFilters);

    if (searchParams) {
      const searchResponse = await apiFetch<InventorySearchPayload>(`/inventory/search?${searchParams.toString()}`);
      if (searchResponse.status === "ok") {
        const contextualMatches = (searchResponse.data.items || [])
          .filter((item) => item.vin !== currentVehicle.vin)
          .slice(0, 8)
          .map(mapSearchItemToSimilarVehicle);

        if (contextualMatches.length) {
          setSimilar(contextualMatches);
          return;
        }
      }
    }

    const fallbackResponse = await apiFetch<SimilarVehicle[]>(
      `/inventory/${encodeURIComponent(currentVehicle.vin)}/similar?limit=8`,
    );
    if (fallbackResponse.status === "ok") {
      setSimilar(fallbackResponse.data);
      return;
    }

    setSimilar([]);
  }

  async function loadMarketComparison(currentVehicle: VehicleDetail) {
    setMarketComparisonLoading(true);
    const response = await apiFetch<MarketComparisonData>(
      `/inventory/${encodeURIComponent(currentVehicle.vin)}/market-comparison`,
    );
    if (response.status === "ok") {
      setMarketComparison(response.data);
    } else {
      setMarketComparison(null);
    }
    setMarketComparisonLoading(false);
  }

  useEffect(() => {
    async function loadVehicle() {
      setLoading(true);
      setError(null);
      const token = auth?.accessToken || undefined;
      const response = await apiFetch<VehicleDetail>(
        `/inventory/${encodeURIComponent(vin)}`,
        undefined,
        token,
      );
      if (response.status !== "ok") {
        setVehicle(null);
        setError(response.error?.message || "Unable to load vehicle details.");
        setLoading(false);
        return;
      }
      setVehicle(response.data);
      setGalleryIndex(0);
      setPhotoModalIndex(null);
      setShowAllFeatures(false);
      setDownPaymentInput("");
      setMarketComparison(null);
      setReportStatus(response.data.has_inspection_report ? "available" : "none");
      setLoading(false);
      void loadSimilarListings(response.data);
      void loadMarketComparison(response.data);
    }
    void loadVehicle();
  }, [vin, auth]);

  useEffect(() => {
    if (loading || topResetVin.current === vin || typeof window === "undefined") return;
    topResetVin.current = vin;
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loading, vin]);

  useEffect(() => {
    if (photoModalIndex === null && !showPriceModal) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPhotoModalIndex(null);
        setShowPriceModal(false);
        return;
      }
      if (photoModalIndex === null || !vehicle) return;

      const displayImages = resolveDisplayImages(vehicle);
      if (displayImages.length < 2) return;

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setPhotoModalIndex((current) => getPreviousIndex(current ?? 0, displayImages.length));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setPhotoModalIndex((current) => getNextIndex(current ?? 0, displayImages.length));
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [photoModalIndex, showPriceModal, vehicle]);

  if (loading) {
    return (
      <div className="vdp-wrap">
        <a className="vdp-back-link" href="#" onClick={(e) => { e.preventDefault(); window.history.back(); }}>
          &larr; Go back
        </a>
        <section className="card">Loading vehicle details...</section>
      </div>
    );
  }

  if (error || !vehicle) {
    return (
      <div className="vdp-wrap">
        <a className="vdp-back-link" href="#" onClick={(e) => { e.preventDefault(); window.history.back(); }}>
          &larr; Go back
        </a>
        <section className="card">{error || "Vehicle not found."}</section>
      </div>
    );
  }

  const currentVehicle = vehicle;
  const displayImages = resolveDisplayImages(vehicle);
  const nhtsa = vehicle.nhtsa_decoded;
  const odometerStr = vehicle.odometer != null
    ? `${vehicle.odometer.toLocaleString()} ${vehicle.odometer_units || "mi"}`
    : null;

  const specsItems: NhtsaCategoryItem[] = nhtsa?.specs?.length ? nhtsa.specs : buildFallbackSpecs(vehicle);
  const buildItems: NhtsaCategoryItem[] = nhtsa?.build || [];
  const structuredFeatureDetails = mergeStructuredFeatureDetails(
    vehicle.feature_details || [],
    vehicle.high_value_feature_details || [],
    vehicle.option_details || [],
    vehicle.option_package_details || [],
  );
  const expandedFeatureBadges = buildExpandedFeatureBadges(vehicle, structuredFeatureDetails);
  const categorized = categorizeFeatures(expandedFeatureBadges, nhtsa, structuredFeatureDetails);
  const mergedSpecsItems = mergeCategoryItems(specsItems, buildItems, 6);
  const pricingBreakdown = buildVehiclePriceBreakdown({
    sourcePrice: vehicle.source_price,
    buyFee: vehicle.buy_fee,
    priceWholesaleEstimate: vehicle.price_wholesale_est,
    fallbackAdvertisedPrice: vehicle.price_asking,
  });
  const pricingDetails = {
    ...pricingBreakdown,
    total: pricingBreakdown.cashPrice,
  };
  const selectedTier = getCreditTierDefinition(selectedCreditTier);
  const downPayment = parseDownPaymentInput(downPaymentInput, pricingDetails.total);
  const financedAmount = Math.max(pricingDetails.total - downPayment.amount, 0);
  const estimatedMonthlyPayment = estimateMonthlyPayment(financedAmount, selectedTier.apr, DEFAULT_LOAN_TERM_MONTHS);
  const pricingBadge = resolvePricingBadge(vehicle, pricingDetails.total);
  const disclosureText = buildDisclosureText();
  const vehicleTitle = `Used ${vehicle.year} ${vehicle.make} ${vehicle.model}${vehicle.trim ? ` ${vehicle.trim}` : ""}${vehicle.drivetrain ? ` ${vehicle.drivetrain}` : ""}`;
  const quickFacts = [
    odometerStr ? { label: odometerStr } : null,
    vehicle.body_type ? { label: vehicle.body_type } : null,
    vehicle.transmission || vehicle.transmission_type ? { label: vehicle.transmission || vehicle.transmission_type || "" } : null,
    vehicle.fuel_type ? { label: vehicle.fuel_type } : null,
    vehicle.exterior_color ? { label: `${vehicle.exterior_color} Exterior`, color: colorToHex(vehicle.exterior_color) } : null,
    vehicle.interior_color ? { label: `${vehicle.interior_color} Interior`, color: colorToHex(vehicle.interior_color) } : null,
    { label: `VIN ${maskVin(vehicle.vin, isAdminUser(auth) || (isPreapproved && inGarage))}` },
  ].filter(Boolean) as Array<{ label: string; color?: string }>;
  const galleryMain = displayImages[galleryIndex] || resolveHeroImage(vehicle) || FALLBACK_IMAGE;
  const previewIndices = getPreviewIndices(displayImages.length, galleryIndex);
  const activeModalIndex = photoModalIndex ?? galleryIndex;
  const activeModalImage = displayImages[activeModalIndex] || galleryMain;
  const vehicleSold = !vehicle.available && inGarage;

  function prevGallery() {
    if (displayImages.length < 2) return;
    setGalleryIndex((current) => getPreviousIndex(current, displayImages.length));
  }

  function nextGallery() {
    if (displayImages.length < 2) return;
    setGalleryIndex((current) => getNextIndex(current, displayImages.length));
  }

  function openPhotoModal(index: number) {
    setPhotoModalIndex(index);
  }

  function closePhotoModal() {
    setPhotoModalIndex(null);
  }

  function prevModalImage() {
    setPhotoModalIndex((current) => getPreviousIndex(current ?? 0, displayImages.length));
  }

  function nextModalImage() {
    setPhotoModalIndex((current) => getNextIndex(current ?? 0, displayImages.length));
  }

  function handlePhotoTouchStart(event: TouchEvent<HTMLDivElement>) {
    photoTouchStartX.current = event.touches[0]?.clientX ?? null;
  }

  function handlePhotoTouchEnd(event: TouchEvent<HTMLDivElement>) {
    if (displayImages.length < 2 || photoTouchStartX.current === null) return;
    const endX = event.changedTouches[0]?.clientX;
    if (endX === undefined) return;
    const deltaX = endX - photoTouchStartX.current;
    photoTouchStartX.current = null;
    if (Math.abs(deltaX) < 40) return;
    if (deltaX > 0) prevModalImage();
    else nextModalImage();
  }

  async function addToGarage(tokenOverride?: string) {
    const token = tokenOverride || auth?.accessToken;
    if (!token) {
      setPendingAction("garage");
      setShowAuthModal(true);
      return;
    }
    setActionLoading("garage");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch<{
      ove_detail_refresh?: { queued?: boolean; deduplicated?: boolean } | null;
    }>(`/me/garage/${encodeURIComponent(currentVehicle.vin)}`, { method: "POST" }, token);
    if (handleUnauthorized(response)) { setActionLoading(null); return; }
    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to save vehicle to garage.");
      setActionLoading(null);
      return;
    }
    setActionMessage(
      response.data.ove_detail_refresh?.queued
        ? response.data.ove_detail_refresh.deduplicated
          ? "Vehicle saved. Inspection details are already being refreshed."
          : "Vehicle saved. Inspection details have been requested."
        : "Vehicle saved to My Garage."
    );
    setActionLoading(null);
    const refreshed = await apiFetch<VehicleDetail>(
      `/inventory/${encodeURIComponent(currentVehicle.vin)}`,
      undefined,
      token,
    );
    if (refreshed.status === "ok") {
      setVehicle(refreshed.data);
      setGalleryIndex(0);
      setReportStatus(refreshed.data.has_inspection_report ? "available" : "none");
    }
  }

  async function startAcquisition(tokenOverride?: string) {
    const token = tokenOverride || auth?.accessToken;
    if (!token) {
      setPendingAction("acquire");
      setShowAuthModal(true);
      return;
    }
    setActionLoading("acquire");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch(
      `/me/garage/${encodeURIComponent(currentVehicle.vin)}/acquire`,
      { method: "POST" },
      token,
    );
    if (handleUnauthorized(response)) { setActionLoading(null); return; }
    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to start purchase.");
      setActionLoading(null);
      return;
    }
    setActionMessage("Purchase started. Redirecting to My Garage.");
    setActionLoading(null);
    window.location.href = `/dashboard?vin=${encodeURIComponent(currentVehicle.vin)}`;
  }

  async function requestConditionReport(tokenOverride?: string) {
    const token = tokenOverride || auth?.accessToken;
    if (!token) {
      setPendingAction("cr");
      setShowAuthModal(true);
      return;
    }
    setActionLoading("condition-report");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch<{
      message?: string;
      already_available?: boolean;
      status?: string;
      request_id?: string;
      deduplicated?: boolean;
    }>(
      `/me/vehicles/${encodeURIComponent(currentVehicle.vin)}/condition-report-request`,
      { method: "POST" },
      token,
    );
    if (handleUnauthorized(response)) { setActionLoading(null); return; }
    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to request inspection report.");
      setActionLoading(null);
      return;
    }
    if (response.data.status === "available" || response.data.already_available) {
      setVehicle({ ...currentVehicle, has_inspection_report: true });
      setReportStatus("available");
    } else if (response.data.deduplicated || response.data.request_id) {
      setReportStatus("pending");
    }
    setActionMessage(
      response.data.message ||
        (response.data.already_available
          ? "Inspection report is already available for this vehicle."
          : "Inspection report requested. Refresh this page after the report is ready.")
    );
    setActionLoading(null);
  }

  const featureLimit = showAllFeatures ? expandedFeatureBadges.length : 24;
  const isAuction = vehicle.source_type === "ove" || vehicle.source_type === "auction";
  const sellerSummary = sanitizePublicText((vehicle.seller_comments || "").trim()) || buildFallbackSellerSummary(vehicle);
  const hotDeal = vehicle.hot_deal;

  return (
    <div className="vdp-wrap">
      <a className="vdp-back-link" href="#" onClick={(e) => { e.preventDefault(); window.history.back(); }}>
        &larr; Go back
      </a>
      {hotDeal ? (
        <div className="vdp-hot-deal-banner">
          <div>
            <span className="hot-deal-pill">Deal of the Hour</span>
            <strong>{hotDeal.deal_label} Deal</strong>
            <span>{formatCurrency(hotDeal.deal_delta)} below MMR</span>
          </div>
          <span className="vdp-hot-deal-countdown">{formatHotDealCountdown(hotDeal.auction_end_at, countdownNow)}</span>
        </div>
      ) : null}

      <section className="card vdp-hero-card">
        <div className="vdp-hero-grid">
          <div className="vdp-gallery-shell">
            <div className="vdp-gallery-grid">
              <div className={`vdp-gallery-stage${vehicleSold ? " is-sold" : ""}`} style={showroomContainerStyle(galleryMain)} onClick={() => openPhotoModal(galleryIndex)} role="button" tabIndex={0} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openPhotoModal(galleryIndex);
                }
              }}>
                <img
                  src={galleryMain}
                  alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                  className={showroomImageClassName(galleryMain)}
                  style={showroomImageStyle(galleryMain)}
                />
                {vehicleSold ? (
                  <div className="vdp-sold-overlay">
                    <span className="vdp-sold-overlay-text">SOLD</span>
                  </div>
                ) : null}
                {displayImages.length > 1 ? (
                  <>
                  <button className="vdp-gallery-arrow vdp-gallery-arrow-left" type="button" aria-label="Previous photo" onClick={(event) => { event.stopPropagation(); prevGallery(); }}>
                    &lsaquo;
                  </button>
                    <button className="vdp-gallery-arrow vdp-gallery-arrow-right" type="button" aria-label="Next photo" onClick={(event) => { event.stopPropagation(); nextGallery(); }}>
                      &rsaquo;
                    </button>
                  </>
                ) : null}
              </div>

              <div className="vdp-gallery-preview-stack">
                {previewIndices.map((index) => {
                  const image = displayImages[index] || galleryMain;
                  return (
                    <button
                      key={`${image}-${index}`}
                      className={`vdp-gallery-preview${vehicleSold ? " is-sold" : ""}`}
                      style={showroomContainerStyle(image)}
                      onClick={() => setGalleryIndex(index)}
                    >
                      <img
                        src={image}
                        alt={`Vehicle preview ${index + 1}`}
                        loading="lazy"
                        className={showroomImageClassName(image)}
                        style={showroomImageStyle(image)}
                      />
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="vdp-gallery-footer">
              <div className="vdp-gallery-counts">
                <span>{displayImages.length} Photos</span>
                <span>{galleryIndex + 1} of {displayImages.length}</span>
              </div>
              <button className="vdp-link-button" onClick={() => openPhotoModal(galleryIndex)}>
                See all photos
              </button>
            </div>
          </div>

          <aside className="vdp-purchase-panel">
            <div className="vdp-price-header">
              <div>
                <span className="vdp-price-pill">{pricingBadge}</span>
                <div className="vdp-price-row">
                  <strong className="vdp-price-amount">{formatCurrency(pricingDetails.total)}</strong>
                  <button className="vdp-link-button" onClick={() => setShowPriceModal(true)}>
                    See price details
                  </button>
                </div>
                <p className="vdp-price-disclaimer">* Taxes, title, registration, and transport are excluded.</p>
                <p className="vdp-price-subtitle">
                  {toPublicSourceLabel(vehicle.source_label, vehicle.source_type)}
                  {vehicle.condition_grade ? ` • Grade ${vehicle.condition_grade}` : ""}
                </p>
                {vehicle.badges && vehicle.badges.length > 0 && (
                  <div className="inventory-badges" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    {vehicle.badges.map((b) => (
                      <span key={b.type} className={`badge badge--${b.color}`} title={b.ratio ? `Price/MMR: ${b.ratio}` : undefined}>
                        {b.label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="vdp-payment-options">
              <div className="vdp-payment-choice active vdp-finance-card">
                <span className="vdp-payment-choice-label">Finance</span>
                <strong>{formatCurrency(estimatedMonthlyPayment)}/mo</strong>
                <small>{formatCurrency(financedAmount)} financed over {DEFAULT_LOAN_TERM_MONTHS} months</small>
              </div>
              <label className="vdp-payment-card vdp-down-payment-card">
                <span>Choose Your Down Payment</span>
                <input
                  className="input vdp-down-payment-input"
                  type="text"
                  inputMode="text"
                  value={downPaymentInput}
                  onChange={(event) => setDownPaymentInput(event.target.value)}
                  placeholder="$7,000 or 10%"
                  aria-label="Choose your down payment"
                />
                <small className="vdp-down-payment-help">
                  {downPayment.kind === "none"
                    ? "You may enter $ amount or %"
                    : `Using ${formatCurrency(downPayment.amount)} down payment${downPayment.kind === "percent" ? ` (${downPayment.percentValue.toFixed(2)}%)` : ""}`}
                </small>
              </label>
            </div>

            <label className="vdp-credit-field">
              <span>Estimated credit score</span>
              <select
                className="select vdp-credit-select"
                value={selectedCreditTier}
                onChange={(event) => setSelectedCreditTier(event.target.value as CreditTierId)}
              >
                {CREDIT_TIER_DEFINITIONS.map((tier) => (
                  <option key={tier.id} value={tier.id}>
                    {tier.label}
                  </option>
                ))}
              </select>
            </label>

            <p className="vdp-payment-disclosure">
              Estimated using {selectedTier.apr.toFixed(2)}% APR for {DEFAULT_LOAN_TERM_MONTHS} months
              {downPayment.amount > 0 ? ` with ${formatCurrency(downPayment.amount)} down payment` : " with no down payment"}.
            </p>

            <div className="vdp-disclosure-card">
              <h3>VirtualCarHub Disclosure</h3>
              <p>{disclosureText}</p>
            </div>
          </aside>
        </div>
      </section>

      <section className="vdp-detail-shell">
        <div className={`vdp-detail-grid${similar.length ? "" : " no-sidebar"}`}>
          <div className="vdp-detail-main">
            <section className="card vdp-listing-card">
              <div className="vdp-listing-header">
                <div>
                  <h1 className="vdp-title">{vehicleTitle}</h1>
                  {(vehicle.location_state || vehicle.location_zip) ? (
                    <p className="vdp-location">
                      {vehicle.location_state}{vehicle.location_zip ? `, ${vehicle.location_zip}` : ""}
                    </p>
                  ) : null}
                </div>
                <span className="vdp-listing-source">{toPublicSourceLabel(vehicle.source_label, vehicle.source_type)}</span>
              </div>

              <div className="vdp-facts-strip">
                {quickFacts.map((fact) => (
                  <span className="vdp-fact-pill" key={fact.label}>
                    {fact.color ? <span className="vdp-color-dot" style={{ background: fact.color }} /> : null}
                    {fact.label}
                  </span>
                ))}
              </div>

              <div className="vdp-action-row">
                {vehicle.is_in_garage ? (
                  <button className="vdp-action-btn vdp-action-primary" disabled>In My Garage</button>
                ) : (
                  <button className="vdp-action-btn vdp-action-primary" onClick={() => addToGarage()} disabled={actionLoading !== null}>
                    {actionLoading === "garage" ? "Saving..." : "Save to My Garage"}
                  </button>
                )}

                <button className="vdp-action-btn vdp-action-dark" onClick={() => startAcquisition()} disabled={actionLoading !== null}>
                  {actionLoading === "acquire" ? "Starting..." : "Start Purchase"}
                </button>

                {auth && !vehicle.has_inspection_report && reportStatus !== "pending" ? (
                  <button className="vdp-action-btn vdp-action-accent" onClick={() => requestConditionReport()} disabled={actionLoading !== null}>
                    {actionLoading === "condition-report" ? "Requesting..." : "Request Inspection Report"}
                  </button>
                ) : null}

                {auth && reportStatus === "pending" ? (
                  <button className="vdp-action-btn vdp-action-outline" disabled>Inspection Report Pending</button>
                ) : null}

                {auth && (vehicle.has_inspection_report || reportStatus === "available") ? (
                  <Link className="vdp-action-btn vdp-action-outline" href={`/vinventory/${encodeURIComponent(vehicle.public_slug || vehicle.vin)}/condition-report` as any}>
                    View Inspection Report
                  </Link>
                ) : null}

                {vehicle.source_url ? (
                  <a className="vdp-action-btn vdp-action-outline" href={vehicle.source_url} target="_blank" rel="noreferrer">
                    Original Listing
                  </a>
                ) : null}
              </div>

              {actionError ? <p className="vdp-error">{actionError}</p> : null}
              {actionMessage ? <p className="vdp-msg">{actionMessage}</p> : null}
            </section>

            <div className="vdp-specs-layout">
              <div className="vdp-cards-grid">
                <CategoryCard title="Specs" icon={<IconSpecs />} items={mergedSpecsItems} color="#c05621" />
                <CategoryCard title="Highlights" icon={<IconHighlights />} items={categorized.highlights} color="#c05621" />
                <CategoryCard title="Safety Features" icon={<IconSafety />} items={categorized.safety} color="#c05621" />
                <CategoryCard title="Exterior" icon={<IconExterior />} items={categorized.exterior} color="#c05621" />
                <CategoryCard title="Interior Features" icon={<IconInterior />} items={categorized.interior} color="#c05621" />
                <CategoryCard title="Technology Features" icon={<IconTechnology />} items={categorized.technology} color="#c05621" />
              </div>
            </div>

            {expandedFeatureBadges.length > 0 ? (
              <section className="card vdp-features-card">
                {showAllFeatures ? (
                  <div className="inventory-feature-grid vdp-feature-grid">
                    {expandedFeatureBadges.slice(0, featureLimit).map((feature) => (
                      <span className="badge" key={feature}>{feature}</span>
                    ))}
                  </div>
                ) : null}
                <button className="vdp-view-all-btn" onClick={() => setShowAllFeatures(!showAllFeatures)}>
                  {showAllFeatures ? "Hide Features" : "View All Features"}
                </button>
              </section>
            ) : null}

            {sellerSummary ? (
              <section className="card vdp-summary-card">
                <div className="vdp-summary-header">
                  <div>
                    <h3>VirtualCarHub Listing Summary</h3>
                    <p>
                      {vehicle.seller_comments
                        ? "Curated from listing data for VirtualCarHub shoppers."
                        : "Generated from verified vehicle data."}
                    </p>
                  </div>
                  <div className="inventory-feature-grid vdp-summary-badges">
                    {(vehicle.city || vehicle.location_state) ? (
                      <span className="badge">
                        {[vehicle.city, vehicle.location_state].filter(Boolean).join(", ")}
                      </span>
                    ) : null}
                    {/* dealer_name hidden — must not expose sourcing partner identity */}
                    {vehicle.source_label ? <span className="badge">{toPublicSourceLabel(vehicle.source_label, vehicle.source_type)}</span> : null}
                  </div>
                </div>
                <p className="vdp-summary-copy">{sellerSummary}</p>
              </section>
            ) : null}

            <ValueComparisonDemandCard data={marketComparison} loading={marketComparisonLoading} />

            {vehicle.display_context?.dealer_photos_gated ? (
              <section className="card vdp-gated-card">
                <h3>More Images Available</h3>
                {!auth?.accessToken ? (
                  <>
                    <p>Sign in and add this vehicle to your garage to view additional photos.</p>
                    <button className="vdp-action-btn vdp-action-primary" onClick={() => setShowAuthModal(true)}>
                      Sign In to View
                    </button>
                  </>
                ) : !vehicle.is_in_garage ? (
                  <>
                    <p>Add this vehicle to My Garage to unlock additional dealer photos.</p>
                    <button className="vdp-action-btn vdp-action-primary" onClick={() => addToGarage()} disabled={actionLoading !== null}>
                      {actionLoading === "garage" ? "Adding..." : "Add to My Garage"}
                    </button>
                  </>
                ) : null}
              </section>
            ) : null}

          </div>

          {similar.length ? (
            <aside className="card vdp-similar-rail">
              <div className="vdp-similar-header-bar">
                <h2 className="vdp-similar-title">Similar Listings</h2>
                <span className="vdp-similar-count">{similar.length} results</span>
              </div>

              <div className="vdp-similar-scroll">
                {similar.map((item) => {
                  const image = item.hero_image || FALLBACK_IMAGE;
                  return (
                    <Link key={item.vin} href={`/vinventory/${encodeURIComponent(item.public_slug || item.vin)}` as any} className="vdp-similar-card">
                      <div
                        className="vdp-similar-img-wrap"
                        style={{ background: `url(${SHOWROOM_BG}) center bottom / cover no-repeat` }}
                      >
                        <img
                          src={image}
                          alt={`${item.year} ${item.make} ${item.model}`}
                          className="vdp-similar-showroom-img"
                        />
                      </div>
                      <div className="vdp-similar-info">
                        <div className="vdp-similar-topline">
                          <strong>{item.year} {item.make} {item.model}</strong>
                          {item.source_label ? <span className="vdp-similar-source">{item.source_label}</span> : null}
                        </div>
                        <p className="vdp-similar-price">{formatCurrency(item.price_asking)}</p>
                        <p className="vdp-similar-meta">
                          {item.trim || item.body_type || "Vehicle detail available"}
                        </p>
                        <p className="vdp-similar-meta">
                          {item.odometer != null ? `${item.odometer.toLocaleString()} miles` : "Mileage unavailable"}
                          {(item.location_state || item.location_zip) ? ` • ${item.location_state || ""} ${item.location_zip || ""}`.trim() : ""}
                        </p>
                        {(item.exterior_color || item.interior_color) ? (
                          <p className="vdp-similar-colors">
                            {item.exterior_color ? `Exterior: ${item.exterior_color}` : ""}
                            {item.exterior_color && item.interior_color ? " • " : ""}
                            {item.interior_color ? `Interior: ${item.interior_color}` : ""}
                          </p>
                        ) : null}
                        <span className="vdp-similar-view">View details</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </aside>
          ) : null}
        </div>
      </section>

      {photoModalIndex !== null ? (
        <div className="vdp-modal-overlay" onClick={closePhotoModal}>
          <section
            className="card vdp-modal vdp-photo-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="vdp-modal-header">
              <div>
                <h3>Vehicle Photos</h3>
                <p>{activeModalIndex + 1} of {displayImages.length}</p>
              </div>
              <button className="button ghost" onClick={closePhotoModal}>Close</button>
            </header>

            <div
              className={`vdp-photo-stage${vehicleSold ? " is-sold" : ""}`}
              style={showroomContainerStyle(activeModalImage)}
              onTouchStart={handlePhotoTouchStart}
              onTouchEnd={handlePhotoTouchEnd}
            >
              <img
                src={activeModalImage}
                alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                className={showroomImageClassName(activeModalImage)}
                style={showroomImageStyle(activeModalImage)}
              />
              {vehicleSold ? (
                <div className="vdp-sold-overlay">
                  <span className="vdp-sold-overlay-text">SOLD</span>
                </div>
              ) : null}
              {displayImages.length > 1 ? (
                <>
                  <button className="vdp-gallery-nav vdp-gallery-prev" type="button" aria-label="Previous photo" onClick={prevModalImage}>&lsaquo;</button>
                  <button className="vdp-gallery-nav vdp-gallery-next" type="button" aria-label="Next photo" onClick={nextModalImage}>&rsaquo;</button>
                </>
              ) : null}
            </div>

            <div className="vdp-photo-thumbs">
              {displayImages.map((image, index) => (
                <button
                  key={`${image}-${index}`}
                  className={`inventory-thumb${activeModalIndex === index ? " active" : ""}`}
                  onClick={() => setPhotoModalIndex(index)}
                >
                  <img src={image} alt={`Vehicle thumbnail ${index + 1}`} loading="lazy" />
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : null}

      {showPriceModal ? (
        <div className="vdp-modal-overlay" onClick={() => setShowPriceModal(false)}>
          <section
            className="card vdp-modal vdp-pricing-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="vdp-modal-header">
              <div>
                <h3>Price Details</h3>
                <p>Wholesale-based pricing breakdown for this vehicle</p>
              </div>
              <button className="button ghost" onClick={() => setShowPriceModal(false)}>Close</button>
            </header>

            <div className="vdp-price-breakdown">
              <div className="vdp-price-line">
                <span>Vehicle Cost</span>
                <strong>{formatCurrency(pricingDetails.vehicleCost)}</strong>
              </div>
              <div className="vdp-price-line">
                <span>Auction Fee</span>
                <strong>{formatCurrency(pricingDetails.auctionFee)}</strong>
              </div>
              <div className="vdp-price-line">
                <span>Detail Shop</span>
                <strong>{formatCurrency(pricingDetails.detailShopFee)}</strong>
              </div>
              <div className="vdp-price-line">
                <span>VirtualCarHub Service Fee</span>
                <strong>{formatCurrency(pricingDetails.vchFee)}</strong>
              </div>
              <div className="vdp-price-line">
                <span>Marketing & Referral Fund</span>
                <strong>{formatCurrency(pricingDetails.marketingFee)}</strong>
              </div>
              <div className="vdp-price-line total">
                <span>Total Vehicle Price</span>
                <strong>{formatCurrency(pricingDetails.total)}</strong>
              </div>
            </div>

            <p className="vdp-price-footnote">
              * Transport not included. Taxes, title, registration, and lender-specific fees are separate. The Marketing
              & Referral Fund helps cover the cost of finding and closing buyers. When an advocate referral leads to a
              completed purchase, VirtualCarHub shares value back through the Danny Dollar program; more organic and
              referral-driven deals help reduce marketing pressure for everyone.
            </p>
          </section>
        </div>
      ) : null}

      {showAuthModal ? (
        <AuthModal
          onClose={() => { setShowAuthModal(false); setPendingAction(null); }}
          onAuthenticated={(nextAuth) => {
            setAuth(nextAuth);
            setShowAuthModal(false);
            const action = pendingAction;
            setPendingAction(null);
            if (action === "garage") addToGarage(nextAuth.accessToken);
            else if (action === "acquire") startAcquisition(nextAuth.accessToken);
            else if (action === "cr") requestConditionReport(nextAuth.accessToken);
          }}
        />
      ) : null}
    </div>
  );
}

/* ─── Helpers ─── */

function readStoredSearchFilters(): StoredSearchFilters | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(SEARCH_FILTERS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSearchFilters;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function parseDownPaymentInput(value: string, vehiclePrice: number): ParsedDownPayment {
  const trimmed = value.trim();
  if (!trimmed || vehiclePrice <= 0) {
    return { kind: "none", amount: 0, percentValue: 0 };
  }

  const roundMoney = (amount: number): number => Math.round((amount + Number.EPSILON) * 100) / 100;
  const normalized = trimmed.replace(/,/g, "");

  if (normalized.includes("%")) {
    const numeric = Number.parseFloat(normalized.replace(/%/g, "").trim());
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return { kind: "none", amount: 0, percentValue: 0 };
    }

    const percentValue = Math.min(Math.max(numeric, 0), 100);
    return {
      kind: "percent",
      amount: roundMoney((vehiclePrice * percentValue) / 100),
      percentValue,
    };
  }

  const numeric = Number.parseFloat(normalized.replace(/\$/g, "").trim());
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return { kind: "none", amount: 0, percentValue: 0 };
  }

  return {
    kind: "cash",
    amount: roundMoney(Math.min(numeric, vehiclePrice)),
    percentValue: 0,
  };
}

function buildStoredSearchParams(filters: StoredSearchFilters | null): URLSearchParams | null {
  if (!filters) return null;

  const s = (v: unknown): string => (v != null ? String(v).trim() : "");
  const params = new URLSearchParams();
  if (s(filters.q)) params.set("q", s(filters.q));
  if (s(filters.make)) params.set("make", s(filters.make));
  if (s(filters.model)) params.set("model", s(filters.model));
  if (s(filters.trim)) params.set("trim", s(filters.trim));
  if (s(filters.body_type)) params.set("body_type", s(filters.body_type));
  if (s(filters.source_type)) params.set("source_type", normalizeSourceFilterValue(String(filters.source_type)));
  if (s(filters.state)) params.set("state", s(filters.state).toUpperCase());
  if (s(filters.zip_code)) params.set("zip_code", s(filters.zip_code));
  if (s(filters.radius)) params.set("radius", s(filters.radius));
  if (s(filters.min_price)) params.set("min_price", s(filters.min_price));
  if (s(filters.max_price)) params.set("max_price", s(filters.max_price));
  if (s(filters.min_year)) params.set("min_year", s(filters.min_year));
  if (s(filters.max_year)) params.set("max_year", s(filters.max_year));
  if (s(filters.min_miles)) params.set("min_miles", s(filters.min_miles));
  if (s(filters.max_miles)) params.set("max_miles", s(filters.max_miles));
  if (s(filters.exterior_color)) params.set("exterior_color", s(filters.exterior_color));
  if (s(filters.interior_color)) params.set("interior_color", s(filters.interior_color));

  if (!Array.from(params.keys()).length) return null;

  params.set("has_images", filters.has_images ? "true" : "false");
  params.set("live_sync", "false");
  params.set("sort_by", filters.sort_by || "updated_at");
  params.set("sort_dir", filters.sort_dir || "desc");
  params.set("page", "1");
  params.set("per_page", "10");

  return params;
}

function mapSearchItemToSimilarVehicle(item: InventorySearchItem): SimilarVehicle {
  return {
    vin: item.vin,
    public_slug: item.public_slug,
    year: item.year,
    make: item.make,
    model: item.model,
    trim: item.trim,
    body_type: item.body_type,
    price_asking: item.price_asking,
    odometer: item.odometer,
    location_state: item.location_state,
    location_zip: item.location_zip,
    exterior_color: item.exterior_color,
    interior_color: item.interior_color,
    source_type: item.source_type,
    source_label: item.source_label,
    hero_image: item.thumbnail,
  };
}

function buildFallbackSpecs(v: VehicleDetail): NhtsaCategoryItem[] {
  const items: NhtsaCategoryItem[] = [];
  if (v.engine_type) items.push({ icon: "engine", text: v.engine_type });
  if (v.cylinders) items.push({ icon: "engine", text: `${v.cylinders} Cylinders` });
  const trans = v.transmission || v.transmission_type;
  if (trans) items.push({ icon: "transmission", text: trans });
  if (v.drivetrain) items.push({ icon: "drivetrain", text: v.drivetrain });
  if (v.fuel_type) items.push({ icon: "fuel", text: v.fuel_type });
  if (v.forced_induction) items.push({ icon: "power", text: v.forced_induction });
  return items;
}

const EXTERIOR_KEYWORDS = [
  "keyless entry", "fog light", "fog lamp", "spoiler", "premium wheel", "alloy wheel",
  "chrome", "roof rack", "running board", "tow hitch", "trailer hitch",
  "power mirror", "heated mirror", "rain sensing", "led headlight", "hid headlight",
  "xenon", "daytime running", "rear spoiler", "power sliding door",
  "power liftgate", "power tailgate", "hands-free liftgate",
  "panoramic roof", "tinted", "privacy glass",
];

const INTERIOR_KEYWORDS = [
  "heated seat", "ventilated seat", "cooled seat", "leather seat", "leather trim",
  "leather steering", "sunroof", "moonroof", "third row", "3rd row",
  "memory seat", "power seat", "bucket seat", "bench seat", "split fold",
  "heated steering", "wood trim", "carbon fiber trim", "ambient light",
  "rear climate", "dual climate", "tri-zone", "dual zone",
  "cup holder", "armrest", "cargo net", "floor mat",
];

const TECHNOLOGY_KEYWORDS = [
  "adaptive cruise", "apple carplay", "android auto", "bluetooth", "keyless start",
  "push button start", "wifi", "wi-fi", "hotspot", "wireless charging",
  "navigation", "gps", "touchscreen", "infotainment", "premium audio", "bose",
  "harman", "jbl", "bang & olufsen", "mark levinson", "burmester",
  "head-up", "heads up", "hud display", "digital cockpit",
  "remote start", "usb", "satellite radio", "siriusxm", "voice control",
  "surround view", "360 camera",
];

const HIGHLIGHT_KEYWORDS = [
  "backup camera", "rear camera", "bluetooth", "apple carplay", "android auto",
  "heated seats", "sunroof", "moonroof", "leather", "navigation", "keyless",
  "remote start", "parking sensor", "premium audio", "bose", "harman",
  "third row", "3rd row", "wifi", "wireless charging", "panoramic",
  "adaptive cruise", "cruise control", "power liftgate", "power tailgate",
  "memory seat", "ventilated seats", "cooled seats", "heads up", "head-up",
  "blind spot", "cross traffic", "brake assist", "security",
];

type CategorizedFeatures = {
  highlights: NhtsaCategoryItem[];
  safety: NhtsaCategoryItem[];
  exterior: NhtsaCategoryItem[];
  interior: NhtsaCategoryItem[];
  technology: NhtsaCategoryItem[];
};

type ParsedDownPayment = {
  kind: "none" | "cash" | "percent";
  amount: number;
  percentValue: number;
};

type FeatureRule = {
  match: string[];
  text?: string;
  bucket?: keyof CategorizedFeatures;
  buckets?: Array<keyof CategorizedFeatures>;
  icon?: string;
  skip?: boolean;
};

function matchesAny(lower: string, keywords: string[]): boolean {
  return keywords.some(kw => lower.includes(kw));
}

function normalizeFeatureKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

function splitFeatureDescriptor(value: string): { category: string | null; description: string } {
  const text = value.trim();
  if (!text.includes("@")) {
    return { category: null, description: text };
  }

  const [prefix, ...rest] = text.split("@");
  const category = prefix.trim();
  const description = rest.join("@").trim();
  if (!category || !description) {
    return { category: null, description: text };
  }

  const normalized = category.toLowerCase();
  const knownCategories = new Set([
    "comfort & convenience",
    "engine",
    "exterior",
    "infotainment",
    "interior",
    "packages",
    "performance",
    "safety & driver assist",
    "technology",
    "transmission",
    "vehicle segment",
  ]);

  if (!knownCategories.has(normalized)) {
    return { category: null, description: text };
  }

  return { category, description };
}

const FEATURE_RULES: FeatureRule[] = [
  { match: ["upgrade paint"], skip: true },
  { match: ["anti collision system"], text: "Pre-Collision System", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["autonomous drive functions"], text: "Driver Assistance Suite", buckets: ["highlights", "technology"], icon: "feature" },
  { match: ["autonomous drive level 2"], text: "Level 2 Driver Assistance", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["blind spot system"], text: "Blind Spot Monitor", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["parking assistance system"], text: "Parking Assist", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["parking distance system"], text: "Front and Rear Parking Sensors", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["cross traffic collision avoidance"], text: "Rear Cross-Traffic Alert", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["traffic information"], text: "Live Traffic Information", bucket: "technology", icon: "power" },
  { match: ["trailer assist"], text: "Trailer Sway Assist", bucket: "safety", icon: "safety" },
  { match: ["rear multi zone air conditioning"], text: "Rear Multi-Zone Climate Control", bucket: "interior", icon: "doors" },
  { match: ["power closing doors"], skip: true },
  { match: ["coming home device"], text: "Approach Lighting", bucket: "exterior", icon: "body" },
  { match: ["adaptive cruise control"], text: "Adaptive Cruise Control", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["power closing liftgate"], text: "Power Liftgate", buckets: ["exterior", "highlights"], icon: "body" },
  { match: ["advanced headlight control functions"], text: "Automatic Headlight Control", bucket: "technology", icon: "power" },
  { match: ["keyless start remote engine start"], text: "Remote Start", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["smart card smart key"], text: "Smart Key", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["sun moonroof", "sunroof", "moonroof"], text: "Sunroof", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["turbo boost"], text: "Turbocharged Engine", bucket: "highlights", icon: "power" },
  { match: ["heated door mirrors"], text: "Heated Side Mirrors", bucket: "exterior", icon: "body" },
  { match: ["fog lights"], text: "Fog Lights", bucket: "exterior", icon: "body" },
  { match: ["upgraded tire type"], skip: true },
  { match: ["upgraded wheel size"], text: "Upgraded Wheel Package", bucket: "exterior", icon: "body" },
  { match: ["premium wheels"], text: "Premium Alloy Wheels", buckets: ["exterior", "highlights"], icon: "body" },
  { match: ["full size suv"], skip: true },
  { match: ["satellite radio"], text: "Satellite Radio", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["bluetooth"], text: "Bluetooth", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["touch screen audio"], text: "Touchscreen Audio System", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["upgraded aux jack input"], skip: true },
  { match: ["upgraded usb connection"], text: "USB Connectivity", bucket: "technology", icon: "power" },
  { match: ["android auto"], text: "Android Auto", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["apple carplay"], text: "Apple CarPlay", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["phone integration"], text: "Smartphone Integration", bucket: "technology", icon: "power" },
  { match: ["steering wheel controls"], text: "Steering Wheel Audio Controls", bucket: "interior", icon: "doors" },
  { match: ["premium speakers"], text: "Premium Audio", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["collision breakdown telematics"], text: "Connected Telematics", bucket: "technology", icon: "power" },
  { match: ["voice recognition"], text: "Voice Recognition", bucket: "technology", icon: "power" },
  { match: ["wireless charging connection"], text: "Wireless Charging", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["virtual assistant"], text: "Voice Assistant", bucket: "technology", icon: "power" },
  { match: ["wifi network"], text: "Wi-Fi Hotspot", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["connected camera"], text: "Surround View Camera", buckets: ["technology", "safety"], icon: "power" },
  { match: ["facial gesture control"], text: "Gesture Controls", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["memory mirrors"], text: "Memory Side Mirrors", buckets: ["exterior", "highlights"], icon: "body" },
  { match: ["memory steering wheel position"], text: "Memory Steering Wheel Position", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["remote hvac control"], text: "Remote Climate Control", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["memory seats"], text: "Memory Seats", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["panoramic sun moonroof"], text: "Panoramic Sunroof", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["head up display"], text: "Head-Up Display", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["navigation", "gps"], text: "Navigation", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["concierge services"], text: "Concierge Services", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["hybrid"], text: "Hybrid Powertrain", buckets: ["technology", "highlights"], icon: "power" },
  { match: ["luxury"], text: "Luxury Trim", bucket: "highlights", icon: "feature" },
  { match: ["heated seat", "heated seats", "heated front seat", "heated front seats"], text: "Heated Front Seats", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["rear parking device"], text: "Rear Parking Sensors", buckets: ["safety", "highlights"], icon: "safety" },
  { match: ["leatherette seats"], text: "SofTex-Trimmed Seats", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["3rd row seats"], text: "3rd-Row Seating", buckets: ["interior", "highlights"], icon: "doors" },
  { match: ["distance object sensing technology"], text: "Proximity Sensors", bucket: "safety", icon: "safety" },
  { match: ["automatic transmission"], skip: true },
];

function resolveFeatureRule(description: string): FeatureRule | null {
  const normalized = normalizeFeatureKey(description);
  return FEATURE_RULES.find((rule) => rule.match.some((term) => normalized.includes(term))) || null;
}

function featureDedupKey(value: string): string {
  const parsed = splitFeatureDescriptor(value);
  const cleaned = parsed.description.trim();
  if (!cleaned) return "";
  const rule = resolveFeatureRule(cleaned);
  return normalizeFeatureKey(rule?.text || cleaned);
}

function inferBucketFromKeywords(description: string): keyof CategorizedFeatures | null {
  const lower = description.toLowerCase();
  if (matchesAny(lower, [
    "adaptive cruise", "blind spot", "collision", "lane ", "parking", "brake assist",
    "cross traffic", "rear camera", "backup camera", "object sensing", "pre-collision",
    "trailer sway", "safety",
  ])) {
    return "safety";
  }
  if (matchesAny(lower, EXTERIOR_KEYWORDS)) return "exterior";
  if (matchesAny(lower, INTERIOR_KEYWORDS)) return "interior";
  if (matchesAny(lower, TECHNOLOGY_KEYWORDS)) return "technology";
  if (matchesAny(lower, HIGHLIGHT_KEYWORDS)) return "highlights";
  return null;
}

function mergeStructuredFeatureDetails(...groups: StructuredFeatureDetail[][]): StructuredFeatureDetail[] {
  const merged: StructuredFeatureDetail[] = [];
  const seen = new Set<string>();

  for (const group of groups) {
    for (const item of group) {
      const description = item?.description?.trim();
      if (!description) continue;
      const key = featureDedupKey(description);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push({
        category: item.category || null,
        description,
        type: item.type || null,
      });
    }
  }

  return merged;
}

function buildExpandedFeatureBadges(vehicle: VehicleDetail, structuredFeatures: StructuredFeatureDetail[]): string[] {
  const merged: string[] = [];
  const seen = new Set<string>();

  function push(value: string | null | undefined) {
    const text = (value || "").trim();
    if (!text) return;
    const key = featureDedupKey(text);
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(text);
  }

  for (const value of vehicle.features_raw || []) push(value);
  for (const item of structuredFeatures) push(item.description);
  for (const value of vehicle.high_value_features || []) push(value);
  for (const value of vehicle.options || []) push(value);
  for (const value of vehicle.option_packages || []) push(value);
  for (const item of vehicle.nhtsa_decoded?.highlights || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.safety || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.exterior || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.interior || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.technology || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.specs || []) push(item.text);
  for (const item of vehicle.nhtsa_decoded?.build || []) push(item.text);

  return merged;
}

/**
 * Strip phone numbers, emails, URLs, and auction house names from text
 * shown to public buyers to prevent leaking wholesale contact details.
 */
function sanitizePublicText(text: string | null | undefined): string {
  if (!text) return "";
  let cleaned = text;
  // Phone numbers (various formats)
  cleaned = cleaned.replace(/(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g, "");
  // Email addresses
  cleaned = cleaned.replace(/[\w.+-]+@[\w.-]+\.\w{2,}/g, "");
  // URLs
  cleaned = cleaned.replace(/https?:\/\/[^\s,)]+/gi, "");
  cleaned = cleaned.replace(/www\.[^\s,)]+/gi, "");
  // Auction house / wholesale marketplace names
  const auctionNames = /\b(Manheim|ADESA|TradeRev|SmartAuction|Smart Auction|Ally\s+Smart\s*Auction|OPENLANE|OVE\.com|ACV\s+Auctions|ACV|BacklotCars|Backlot\s+Cars)\b/gi;
  cleaned = cleaned.replace(auctionNames, "");
  // Collapse leftover whitespace and punctuation artifacts
  cleaned = cleaned.replace(/\s{2,}/g, " ").trim();
  return cleaned;
}

function buildFallbackSellerSummary(vehicle: VehicleDetail): string {
  const parts: string[] = [];
  const title = [vehicle.year, vehicle.make, vehicle.model, vehicle.trim].filter(Boolean).join(" ");
  if (title) {
    parts.push(`This ${title} is presented by VirtualCarHub as a wholesale-direct opportunity.`);
  }

  const specFacts = [
    vehicle.drivetrain,
    vehicle.transmission || vehicle.transmission_type,
    vehicle.fuel_type,
  ].filter(Boolean);
  if (specFacts.length) {
    parts.push(`Configured with ${specFacts.join(", ")}, this listing reflects the latest verified data currently available to VirtualCarHub.`);
  }

  const colorFacts = [vehicle.exterior_color ? `${vehicle.exterior_color} exterior` : null, vehicle.interior_color ? `${vehicle.interior_color} interior` : null]
    .filter(Boolean);
  if (colorFacts.length) {
    parts.push(`The vehicle is shown with ${colorFacts.join(" and ")} styling.`);
  }

  if (vehicle.odometer != null) {
    parts.push(`Reported mileage is ${vehicle.odometer.toLocaleString()} ${vehicle.odometer_units || "mi"}, based on the current inventory record.`);
  }

  parts.push("Feature and inspection details may update as more verified vehicle data becomes available.");
  return parts.join(" ");
}

function featureCategoryBucket(category: string | null | undefined): keyof CategorizedFeatures | null {
  const lower = (category || "").toLowerCase();
  if (!lower) return null;
  if (lower.includes("safety")) return "safety";
  if (lower.includes("exterior")) return "exterior";
  if (lower.includes("interior")) return "interior";
  if (lower.includes("infotainment") || lower.includes("technology")) return "technology";
  if (lower.includes("hybrid") || lower.includes("electric")) return "technology";
  if (
    lower.includes("comfort")
    || lower.includes("convenience")
    || lower.includes("engine")
    || lower.includes("vehicle segment")
    || lower.includes("transmission")
  ) {
    return "highlights";
  }
  return null;
}

function mapFeatureItems(
  description: string,
  category?: string | null,
): Array<{ bucket: keyof CategorizedFeatures; item: NhtsaCategoryItem }> {
  const parsed = splitFeatureDescriptor(description);
  const effectiveCategory = category || parsed.category;
  const cleaned = parsed.description.trim();
  if (!cleaned) return [];

  const rule = resolveFeatureRule(cleaned);
  if (rule?.skip) return [];

  const text = rule?.text || cleaned;
  const derivedBucket = featureCategoryBucket(effectiveCategory) || inferBucketFromKeywords(text);
  const buckets = Array.from(new Set(rule?.buckets || (rule?.bucket ? [rule.bucket] : derivedBucket ? [derivedBucket] : [])));
  if (!buckets.length) return [];

  return buckets.map((bucket) => {
    const icon = rule?.icon
      || (bucket === "safety" ? "safety" : bucket === "technology" ? "power" : bucket === "interior" ? "doors" : bucket === "exterior" ? "body" : "feature");
    return { bucket, item: { icon, text } };
  });
}

function categorizeFeatures(
  features: string[],
  nhtsa: NhtsaDecoded | null | undefined,
  structuredFeatures: StructuredFeatureDetail[],
): CategorizedFeatures {
  const result: CategorizedFeatures = { highlights: [], safety: [], exterior: [], interior: [], technology: [] };
  const used = new Set<string>();
  const safetyTexts = new Set<string>();

  function addItem(bucket: keyof CategorizedFeatures, item: NhtsaCategoryItem, limit = 6): boolean {
    const text = item.text.trim();
    if (!text) return false;
    const key = `${bucket}|${text.toLowerCase()}`;
    if (used.has(key) || result[bucket].length >= limit) return false;
    used.add(key);
    result[bucket].push(item);
    if (bucket === "safety") {
      safetyTexts.add(text.toLowerCase());
    }
    return true;
  }

  for (const item of nhtsa?.safety || []) addItem("safety", item);
  for (const item of nhtsa?.highlights || []) addItem("highlights", item);
  for (const item of nhtsa?.exterior || []) addItem("exterior", item);
  for (const item of nhtsa?.interior || []) addItem("interior", item);
  for (const item of nhtsa?.technology || []) addItem("technology", item);

  for (const detail of structuredFeatures) {
    const mappedItems = mapFeatureItems(detail.description, detail.category);
    for (const mapped of mappedItems) {
      if (mapped.bucket === "safety" && safetyTexts.has(mapped.item.text.toLowerCase())) continue;
      addItem(mapped.bucket, mapped.item);
    }
  }

  for (const feat of features) {
    const mappedItems = mapFeatureItems(feat);
    for (const mapped of mappedItems) {
      if (mapped.bucket === "safety" && safetyTexts.has(mapped.item.text.toLowerCase())) continue;
      addItem(mapped.bucket, mapped.item);
    }
  }

  return result;
}

function colorToHex(name: string): string {
  const map: Record<string, string> = {
    black: "#1a1a1a", white: "#f5f5f5", silver: "#c0c0c0", gray: "#808080", grey: "#808080",
    red: "#c62828", blue: "#1565c0", green: "#2e7d32", brown: "#5d4037", beige: "#d4c5a9",
    gold: "#c6a600", orange: "#e65100", yellow: "#f9a825", purple: "#6a1b9a", tan: "#d2b48c",
    maroon: "#800000", burgundy: "#800020", charcoal: "#36454f", pearl: "#eae0c8",
    champagne: "#f7e7ce", ivory: "#fffff0", bronze: "#cd7f32", magnetic: "#4a4a4a",
  };
  const lower = name.toLowerCase();
  for (const [key, hex] of Object.entries(map)) {
    if (lower.includes(key)) return hex;
  }
  return "#9e9e9e";
}

function resolveDisplayImages(vehicle: VehicleDetail | null | undefined): string[] {
  if (!vehicle) return [];
  const ctx = vehicle.display_context;
  const hero = resolveHeroImage(vehicle);
  const supplemental = vehicle.supplemental_photo_links || vehicle.photo_links_cached || vehicle.photo_links || [];
  const referenceDetail = ctx?.reference_detail_images || [];
  if (referenceDetail.length) {
    const base = ctx?.gallery_images || vehicle.display_images || [];
    const seen = new Set(referenceDetail);
    const merged = [hero, ...base.filter((url: string) => !seen.has(url)), ...referenceDetail, ...supplemental];
    return Array.from(new Set(merged.filter(Boolean) as string[]));
  }
  const extStills = ctx?.evox_exterior_stills || [];
  const intStills = ctx?.evox_interior_stills || [];
  const intPano = ctx?.evox_interior_pano || [];
  if (extStills.length || intStills.length || intPano.length) {
    const base = ctx?.gallery_images || vehicle.display_images || [];
    const curatedExt = extStills.filter((_: string, i: number) => i % 4 === 0);
    const evoxDetail = [...curatedExt, ...intStills, ...intPano];
    const seen = new Set(evoxDetail);
    const merged = [hero, ...base.filter((url: string) => !seen.has(url)), ...evoxDetail, ...supplemental];
    return Array.from(new Set(merged.filter(Boolean) as string[]));
  }
  const primary = vehicle.display_images || ctx?.gallery_images || [];
  if (primary.length) {
    return Array.from(new Set([hero, ...primary, ...supplemental].filter(Boolean) as string[]));
  }
  return Array.from(new Set([hero, ...(vehicle.images || []), ...supplemental].filter(Boolean) as string[]));
}

function resolveHeroImage(vehicle: VehicleDetail | null | undefined): string | null {
  if (!vehicle) return null;
  return vehicle.hero_image || vehicle.display_context?.hero_image || null;
}

function getNextIndex(current: number, length: number): number {
  if (length <= 1) return 0;
  return (current + 1) % length;
}

function getPreviousIndex(current: number, length: number): number {
  if (length <= 1) return 0;
  return (current - 1 + length) % length;
}

function getPreviewIndices(length: number, activeIndex: number): number[] {
  if (length <= 1) return [];
  const indices: number[] = [];
  for (let step = 1; step < length && indices.length < 2; step += 1) {
    indices.push((activeIndex + step) % length);
  }
  return indices;
}

function mergeCategoryItems(primary: NhtsaCategoryItem[], secondary: NhtsaCategoryItem[], limit = 6): NhtsaCategoryItem[] {
  const merged: NhtsaCategoryItem[] = [];
  const seen = new Set<string>();

  for (const group of [primary, secondary]) {
    for (const item of group) {
      const key = item.text.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(item);
      if (merged.length >= limit) return merged;
    }
  }

  return merged;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function formatHotDealCountdown(target: string, now: number): string {
  const remaining = Math.max(0, new Date(target).getTime() - now);
  const totalSeconds = Math.floor(remaining / 1000);
  if (totalSeconds <= 0) return "Expired";
  if (totalSeconds < 60) return "Ending now";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours < 1) {
    return `Final minutes ${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `Ends in ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function resolvePricingBadge(vehicle: VehicleDetail, displayedPrice: number): string {
  if (vehicle.price_wholesale_est && displayedPrice <= vehicle.price_wholesale_est * 1.08) {
    return "Good Price";
  }
  if ((vehicle.source_type || "").toLowerCase() === "ove" || (vehicle.source_type || "").toLowerCase() === "auction") {
    return "Wholesale Direct";
  }
  return "Transparent Price";
}

function buildDisclosureText(): string {
  return "Some wholesale inventory images cannot be shown publicly. When that happens, VirtualCarHub may use reference images based on year, make, model, and trim. Color and condition may be approximate. Sign in, save the vehicle to My Garage, and request an inspection report to see the most accurate vehicle details available.";
}
