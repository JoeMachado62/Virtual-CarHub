/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FaArrowLeft,
  FaCar,
  FaChevronDown,
  FaChevronLeft,
  FaChevronRight,
  FaCircleDot,
  FaFileLines,
  FaGaugeHigh,
  FaListCheck,
  FaPrint,
  FaTriangleExclamation,
  FaUpRightAndDownLeftFromCenter,
  FaWrench,
} from "react-icons/fa6";

import { apiFetch } from "@/lib/api";
import { isAdminUser, loadValidAuthState } from "@/lib/auth";
import { maskVin } from "@/lib/vin";

type VehicleDetail = {
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  engine_type?: string | null;
  drivetrain?: string | null;
  odometer?: number | null;
  price_asking: number;
  location_zip?: string | null;
  location_state?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  source_url?: string | null;
  exterior_color?: string | null;
  interior_color?: string | null;
  transmission?: string | null;
  fuel_type?: string | null;
  odometer_units?: string | null;
  auction_house?: string | null;
  pickup_location?: string | null;
  inventory_status?: string | null;
  inventory_label?: string | null;
  condition_grade?: string | null;
  condition_report_grade?: string | null;
  seller_comments?: string | null;
  condition_report?: Record<string, unknown>;
  condition_report_url?: string | null;
  listing_snapshot?: Record<string, unknown>;
  hero_image?: string | null;
  images: string[];
  display_images?: string[];
  display_context?: {
    hero_image?: string | null;
    gallery_images?: string[];
    inspection_images?: string[];
    disclosure_images?: string[];
    condition_report?: Record<string, unknown>;
    disclaimer?: string;
  };
  mmr?: number | null;
  updated_at?: string | null;
  features_normalized?: Record<string, unknown>;
  ove_detail?: {
    seller_comments?: string | null;
    condition_report?: Record<string, unknown>;
    listing_snapshot?: Record<string, unknown>;
    page_url?: string | null;
    images?: Array<{ url: string; role?: string; category?: string; display_order?: number; is_primary?: boolean } | string>;
  };
};

type DamageItem = {
  [key: string]: unknown;
  location?: string;
  section?: string;
  section_label?: string;
  panel?: string;
  damage_type?: string;
  condition?: string;
  description?: string;
  severity?: string;
  reported_severity?: string;
  severity_color?: string;
  severity_label?: string;
  severity_rank?: number;
};

type EquipmentOption = {
  primary_description?: string;
  extended_description?: string;
  classification?: string;
  installed_reason?: string;
  oem_option_code?: string;
  msrp?: number;
  generics?: Array<{ name?: string }>;
};

type AutoCheckReport = {
  scrape_status: "success" | "partial" | "failed" | "not_attempted";
  attempted_at?: string | null;
  autocheck_score?: number | null;
  score_range_low?: number | null;
  score_range_high?: number | null;
  score_range_label?: string | null;
  historical_event_count?: number | null;
  owner_count?: number | null;
  accident_count?: number | null;
  last_reported_event_date?: string | null;
  last_reported_mileage?: number | null;
  title_brand_check?: string | null;
  odometer_check?: string | null;
  accident_check?: string | null;
  damage_check?: string | null;
  other_title_brand_event_check?: string | null;
  vehicle_use?: string | null;
  buyback_protection?: string | null;
  report_logo_url?: string | null;
  full_report_text?: string | null;
  view_report_href?: string | null;
  failure_category?: string | null;
  failure_message?: string | null;
};

type InspectionField = {
  label: string;
  value: string;
  has_issue: boolean;
  is_default?: boolean;
};

type InspectionSection = {
  label: string;
  fields: Record<string, InspectionField>;
  issue_count: number;
};

type Inspection = Record<string, InspectionSection>;

type CategorizedImage = {
  url: string;
  category: string;
  role?: string;
};

type GranularField = {
  label: string;
  group?: string | null;
  status: "normal" | "issue" | "unknown";
  value: string;
  source?: string;
  confidence?: number;
  evidence?: string[];
  image_refs?: string[];
};

type GranularSection = {
  label: string;
  issue_count: number;
  groups?: Record<string, string>;
  fields: Record<string, GranularField>;
};

type GranularInspection = Record<string, GranularSection>;

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";
const AUCTION_DEFAULT = "/assets/images/portfolio/VCH Auction default image.webp";
const TIRES_ICON_IMAGE = "/assets/images/portfolio/tires%20icon.png";

const GRADE_LABELS: Record<string, string> = {
  "5.0": "Extra Clean",
  "4.5": "Clean",
  "4.0": "Clean",
  "3.5": "Average",
  "3.0": "Average",
  "2.5": "Rough",
  "2.0": "Rough",
  "1.5": "Damaged",
  "1.0": "Damaged",
};

const IMAGE_CATEGORIES = [
  { id: "all", label: "ALL" },
  { id: "ext", label: "EXT" },
  { id: "int", label: "INT" },
  { id: "misc", label: "MISC" },
  { id: "dmg", label: "DMG" },
  { id: "video", label: "VIDEO" },
] as const;

const INSPECTION_SECTION_ORDER = ["drivability", "exterior", "interior", "mechanical", "tires"] as const;
const GRANULAR_SECTION_ORDER = ["drivability", "exterior", "interior", "mechanical", "tires"] as const;
const CARFAX_PARTNER_URL = "https://www.carfax.com/VehicleHistory/p/Report.cfx";
const CARFAX_PARTNER_ID = "DVW_1";

const AUTOCHECK_INFO = {
  titleBrand: {
    title: "Major State Title Brand Check",
    body: [
      "Reviews state title records for major brands such as salvage, rebuilt, flood, fire, hail, lemon, junk, manufacturer buyback, and odometer-related title events.",
      "An OK result means AutoCheck did not find a major title brand in the records it received. It does not replace an independent title or DMV verification before purchase.",
    ],
  },
  accident: {
    title: "Accident Check",
    body: [
      "Looks for accident events reported by government, auction, insurance, collision, and other independent data sources available to AutoCheck.",
      "Some accidents are never reported to vehicle-history providers, so this should be read alongside the inspection photos, seller disclosure, and physical condition report.",
    ],
  },
  damage: {
    title: "Damage Check",
    body: [
      "Looks for damage events such as auction announcements, structural notes, insurance-loss records, frame or unibody damage disclosures, and other reported condition events.",
      "Damage severity and location can vary by source, which is why the condition report sections break visible or disclosed damage into more specific vehicle areas.",
    ],
  },
  odometer: {
    title: "Odometer Check",
    body: [
      "Reviews mileage readings and odometer-related events for possible rollbacks, inconsistencies, branded titles, or auction disclosures.",
      "An OK result means AutoCheck did not flag an odometer issue in its available records, but current mileage should still be compared with the listing and inspection.",
    ],
  },
  otherTitleEvent: {
    title: "Other Title Brand and Specific Event Check",
    body: [
      "Covers additional reported events such as theft, repossession, lien, corrected title, duplicate title, insurance loss, auction announcements, or other source-specific disclosures.",
      "These events are not always defects by themselves, but they can affect risk, financing, resale, or buyer confidence.",
    ],
  },
  vehicleUse: {
    title: "Vehicle Usage Check",
    body: [
      "Checks for prior use records such as rental, fleet, lease, taxi, police, government, commercial, or other non-personal usage categories.",
      "Prior use can affect wear patterns and valuation even when the inspection condition is otherwise normal.",
    ],
  },
  buyback: {
    title: "AutoCheck Buyback Protection",
    body: [
      "Indicates whether AutoCheck reports eligibility for its Buyback Protection program based on the data and terms AutoCheck applies.",
      "Eligibility and coverage limits are controlled by AutoCheck. Always review the source report terms before relying on this protection.",
    ],
  },
} as const;

type AutoCheckInfoKey = keyof typeof AUTOCHECK_INFO;

export function ConditionReportDocument({ vin }: { vin: string }) {
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canRevealVin, setCanRevealVin] = useState(false);
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  // Gallery state
  const [galleryIndex, setGalleryIndex] = useState(0);
  const [activeCategory, setActiveCategory] = useState("all");
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [autoCheckInfoKey, setAutoCheckInfoKey] = useState<AutoCheckInfoKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      setLoading(true);
      setError(null);

      // Load auth state first so we can pass the token to the API
      const auth = await loadValidAuthState();
      if (cancelled) return;

      // Check preapproval / admin status to determine CR access
      let preapproved = false;
      if (auth?.accessToken) {
        const [statusRes, garageRes] = await Promise.all([
          apiFetch<{ is_preapproved: boolean }>("/me/account-status", {}, auth.accessToken),
          apiFetch<Array<{ vin: string }>>("/me/garage", {}, auth.accessToken),
        ]);
        if (cancelled) return;
        preapproved = statusRes.status === "ok" && Boolean(statusRes.data?.is_preapproved);
        const inGarage =
          garageRes.status === "ok" &&
          Array.isArray(garageRes.data) &&
          garageRes.data.some((item) => item.vin === vin);
        setCanRevealVin(preapproved && inGarage);
      }

      const adminUser = isAdminUser(auth);
      setIsAdmin(adminUser);
      const hasAccess = adminUser || preapproved;
      setAuthorized(hasAccess);

      if (!hasAccess) {
        setLoading(false);
        return;
      }

      // Fetch vehicle data WITH auth token so backend returns full CR data
      const response = await apiFetch<VehicleDetail>(
        `/inventory/${encodeURIComponent(vin)}`,
        {},
        auth?.accessToken,
      );
      if (cancelled) return;
      if (response.status !== "ok") {
        setVehicle(null);
        setError(response.error?.message || "Unable to load condition report.");
        setLoading(false);
        return;
      }
      setVehicle(response.data);

      setLoading(false);
    }
    void loadData();
    return () => { cancelled = true; };
  }, [vin]);

  const report = useMemo(() => {
    if (!vehicle) return {};
    return vehicle.condition_report || vehicle.display_context?.condition_report || {};
  }, [vehicle]);

  const crUrl = vehicle?.condition_report_url || null;
  const crMetadata = useMemo(() => ((report.metadata || {}) as Record<string, unknown>), [report]);
  const crReportLink = useMemo(() => ((crMetadata.report_link || {}) as Record<string, unknown>), [crMetadata]);
  const crGrade = vehicle?.condition_report_grade || vehicle?.condition_grade || (crReportLink.title as string) || null;
  const gradeLabel = crGrade ? GRADE_LABELS[crGrade] || (parseFloat(crGrade) >= 4.0 ? "Clean" : parseFloat(crGrade) >= 3.0 ? "Average" : "Rough") : null;

  // Images — categorized
  const categorizedImages = useMemo(() => resolveCategorizedImages(vehicle), [vehicle]);
  const filteredImages = useMemo(() => {
    if (activeCategory === "all") return categorizedImages;
    return categorizedImages.filter((img) => img.category === activeCategory);
  }, [categorizedImages, activeCategory]);
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: categorizedImages.length };
    for (const img of categorizedImages) {
      counts[img.category] = (counts[img.category] || 0) + 1;
    }
    return counts;
  }, [categorizedImages]);

  // Reset gallery index when category changes
  useEffect(() => { setGalleryIndex(0); }, [activeCategory]);

  const currentImage = filteredImages[galleryIndex]?.url || AUCTION_DEFAULT;

  const navigateGallery = useCallback((direction: 1 | -1) => {
    if (filteredImages.length === 0) return;
    setGalleryIndex((prev) => (prev + direction + filteredImages.length) % filteredImages.length);
  }, [filteredImages.length]);

  // Keyboard navigation
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") navigateGallery(-1);
      else if (e.key === "ArrowRight") navigateGallery(1);
      else if (e.key === "Escape" && lightboxOpen) setLightboxOpen(false);
      else if (e.key === "Escape" && autoCheckInfoKey) setAutoCheckInfoKey(null);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [navigateGallery, lightboxOpen, autoCheckInfoKey]);

  // Announcements
  const announcements = useMemo(() => parseAnnouncements(report, crMetadata), [report, crMetadata]);
  const remarks = Array.isArray(report.remarks) ? report.remarks.map(String) : [];

  // Inspection — prefer structured, fall back to legacy
  const inspection = useMemo((): Inspection | null => {
    const raw = report.inspection as Inspection | undefined;
    if (raw && typeof raw === "object" && Object.keys(raw).length > 0) return raw;
    return buildLegacyInspection(report);
  }, [report]);
  const visibleInspection = useMemo(() => filterVisibleInspection(inspection), [inspection]);
  const granularInspection = useMemo(() => {
    const raw = report.granular_inspection as GranularInspection | undefined;
    if (raw && typeof raw === "object" && Object.keys(raw).length > 0) return raw;
    return buildGranularInspectionFallback(report, visibleInspection);
  }, [report, visibleInspection]);

  // Title info
  const titleStatus = typeof report.title_status === "string" ? report.title_status : null;
  const titleState = typeof report.title_state === "string" ? report.title_state : null;
  const titleBranding = typeof report.title_branding === "string" ? report.title_branding : null;

  // AutoCheck
  const autocheck = useMemo(() => normalizeAutoCheck(report.autocheck), [report]);
  const autoCheckSummary = useMemo(() => summarizeAutoCheck(autocheck), [autocheck]);
  const activeAutoCheckInfo = autoCheckInfoKey ? AUTOCHECK_INFO[autoCheckInfoKey] : null;

  // Vehicle history
  const vehicleHistory = report.vehicle_history as { engine_starts?: boolean; drivable?: boolean; owners?: number; accidents?: number } | undefined;

  // Damage report
  const damageItems = Array.isArray(report.damage_items) ? (report.damage_items as DamageItem[]) : [];
  const damageSummary = report.damage_summary as { total_items?: number; by_color?: Record<string, number>; structural_issue?: boolean } | undefined;
  const severitySummary = typeof report.severity_summary === "string" ? report.severity_summary : null;

  // Equipment
  const equipmentFeatures = useMemo(
    () => (Array.isArray(report.equipment_features) ? report.equipment_features.map(String) : []),
    [report],
  );
  const installedEquipment = useMemo(
    () => (Array.isArray(report.installed_equipment) ? (report.installed_equipment as EquipmentOption[]) : []),
    [report],
  );
  const highValueOptions = useMemo(
    () => (Array.isArray(report.high_value_options) ? (report.high_value_options as EquipmentOption[]) : []),
    [report],
  );
  const equipmentSection = useMemo(
    () => resolveEquipmentSection({ equipmentFeatures, highValueOptions, installedEquipment }),
    [equipmentFeatures, highValueOptions, installedEquipment],
  );

  // Seller comments
  const sellerCommentsItems = Array.isArray(report.seller_comments_items) ? report.seller_comments_items.map(String) : [];

  // Problem highlights
  const problemHighlights = Array.isArray(report.problem_highlights) ? report.problem_highlights.map(String) : [];

  useEffect(() => {
    if (!granularInspection) return;
    setOpenSections((current) => {
      const next = { ...current };
      for (const sectionId of GRANULAR_SECTION_ORDER) {
        if (next[`granular-${sectionId}`] === undefined) {
          next[`granular-${sectionId}`] = Boolean(granularInspection[sectionId]?.issue_count);
        }
      }
      if (next["title-history"] === undefined) next["title-history"] = true;
      if (next["problem-highlights"] === undefined) next["problem-highlights"] = problemHighlights.length > 0;
      if (next["equipment"] === undefined) next["equipment"] = false;
      if (next["damage"] === undefined) next["damage"] = damageItems.length > 0;
      if (next["vehicle-notes"] === undefined) next["vehicle-notes"] = false;
      return next;
    });
  }, [granularInspection, problemHighlights.length, damageItems.length]);

  // Vehicle info
  const vehicleInfo = useMemo(() => {
    if (!vehicle) return {};
    const norm = vehicle.features_normalized || {};
    const v = vehicle as Record<string, unknown>;
    return {
      exterior_color: String(v.exterior_color || norm.exterior_color || report.exterior_color || ""),
      interior_color: String(v.interior_color || norm.interior_color || report.interior_color || ""),
      engine: String(v.engine_type || norm.engine_type || ""),
      drivetrain: String(v.drivetrain || norm.drivetrain || ""),
      transmission: String(v.transmission || norm.transmission || ""),
      seller: String(vehicle.auction_house || ""),
    };
  }, [vehicle, report]);

  const toggleSection = useCallback((sectionId: string) => {
    setOpenSections((current) => ({ ...current, [sectionId]: !current[sectionId] }));
  }, []);

  const isSectionOpen = useCallback((sectionId: string, defaultOpen = false) => {
    return openSections[sectionId] ?? defaultOpen;
  }, [openSections]);

  if (loading || authorized === null) {
    return (
      <main className="page-stack">
        <section className="card">Loading inspection report...</section>
      </main>
    );
  }

  if (!authorized) {
    return (
      <main className="page-stack">
        <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vin)}` as any}>
          Back to Vehicle
        </Link>
        <section className="card">Inspection reports are available after buyer approval or administrator review.</section>
      </main>
    );
  }

  if (error || !vehicle) {
    return (
      <main className="page-stack">
        <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vin)}` as any}>
          Back to Vehicle
        </Link>
        <section className="card">{error || "Inspection report unavailable."}</section>
      </main>
    );
  }

  return (
    <>
      <main className="page-stack cr-doc">
        {/* ── HEADER ── */}
        <section className="cr-doc-header">
          <div className="cr-doc-header-inner">
            <h2 className="cr-doc-brand">VirtualCarHub Inspection Report</h2>
            <div className="cr-doc-header-actions">
              <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vehicle.public_slug || vehicle.vin)}` as any}>
                <FaArrowLeft aria-hidden="true" /> Back to Vehicle
              </Link>
              {isAdmin && crUrl && (
                <button className="button" onClick={() => window.open(crUrl, "_blank", "noopener,noreferrer")}>
                  See Original Report
                </button>
              )}
              <button className="button ghost" onClick={() => window.print()}><FaPrint aria-hidden="true" /> Print</button>
            </div>
          </div>
        </section>

        {/* ── VEHICLE TITLE BAR ── */}
        <section className="cr-vehicle-title-bar">
          <h1 className="cr-vehicle-name">
            {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim ? `${vehicle.body_type || ""} ${vehicle.trim}`.trim() : vehicle.body_type || ""}
          </h1>
          <div className="cr-vehicle-specs">
            <span>{maskVin(vehicle.vin, authorized || canRevealVin)}</span>
            <span className="cr-spec-sep">&middot;</span>
            <span>Odo {fmtMiles(vehicle.odometer)}</span>
            {vehicleInfo.exterior_color && (
              <>
                <span className="cr-spec-sep">&middot;</span>
                <span>{vehicleInfo.exterior_color} / {vehicleInfo.interior_color || "N/A"}</span>
              </>
            )}
            {vehicleInfo.engine && (
              <>
                <span className="cr-spec-sep">&middot;</span>
                <span>{vehicleInfo.engine}</span>
              </>
            )}
            {vehicleInfo.transmission && (
              <>
                <span className="cr-spec-sep">&middot;</span>
                <span>{vehicleInfo.transmission}</span>
              </>
            )}
            {vehicleInfo.drivetrain && (
              <>
                <span className="cr-spec-sep">&middot;</span>
                <span>{vehicleInfo.drivetrain}</span>
              </>
            )}
          </div>
          {/* Seller/auction house name hidden — wholesale contact details must not be exposed */}
        </section>

        {/* ── GALLERY + SUMMARY PANEL ── */}
        <section className="cr-hero-layout">
          {/* Left: Image Gallery */}
          <div className="cr-gallery">
            <div className="cr-gallery-stage">
              <img
                src={currentImage}
                alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
                className="cr-gallery-main-img"
                onClick={() => setLightboxOpen(true)}
                onError={(e) => { e.currentTarget.src = FALLBACK_IMAGE; }}
              />
              {filteredImages.length > 1 && (
                <>
                  <button className="cr-gallery-arrow cr-gallery-arrow-left" onClick={() => navigateGallery(-1)} aria-label="Previous image"><FaChevronLeft aria-hidden="true" /></button>
                  <button className="cr-gallery-arrow cr-gallery-arrow-right" onClick={() => navigateGallery(1)} aria-label="Next image"><FaChevronRight aria-hidden="true" /></button>
                </>
              )}
              <div className="cr-gallery-counter">
                {filteredImages.length > 0 ? `${galleryIndex + 1} of ${filteredImages.length}` : "No photos"}
                <button className="cr-gallery-fullscreen" onClick={() => setLightboxOpen(true)} aria-label="Full screen"><FaUpRightAndDownLeftFromCenter aria-hidden="true" /></button>
              </div>
            </div>
            {/* Thumbnail strip */}
            <div className="cr-gallery-thumbstrip">
              {filteredImages.slice(0, 20).map((img, i) => (
                <div
                  key={i}
                  className={`cr-gallery-thumb${i === galleryIndex ? " cr-gallery-thumb-active" : ""}`}
                  onClick={() => setGalleryIndex(i)}
                >
                  <img src={img.url} alt={`Thumb ${i + 1}`} onError={(e) => { e.currentTarget.src = FALLBACK_IMAGE; }} />
                </div>
              ))}
            </div>
            {/* Category tabs */}
            <div className="cr-gallery-tabs">
              {IMAGE_CATEGORIES.map((cat) => {
                const count = categoryCounts[cat.id] || 0;
                if (cat.id !== "all" && count === 0) return null;
                return (
                  <button
                    key={cat.id}
                    className={`cr-gallery-tab${activeCategory === cat.id ? " cr-gallery-tab-active" : ""}`}
                    onClick={() => setActiveCategory(cat.id)}
                  >
                    {cat.label}
                    <span className="cr-gallery-tab-count">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: Summary Panel */}
          <div className="cr-summary-panel">
            {/* Grade */}
            {crGrade && (
              <div className="cr-grade-block">
                <div className="cr-grade-circle">
                  <span className="cr-grade-number">{crGrade}</span>
                </div>
                {gradeLabel && <span className="cr-grade-label">{gradeLabel}</span>}
              </div>
            )}

            {/* Announcements */}
            {announcements.length > 0 && (
              <div className="cr-panel-section">
                <h4 className="cr-panel-heading">Announcements</h4>
                <ul className="cr-panel-list">
                  {announcements.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            )}

            {/* Remarks / Comments */}
            {remarks.length > 0 && (
              <div className="cr-panel-section">
                <h4 className="cr-panel-heading">Remarks/Comments</h4>
                <ul className="cr-panel-list">
                  {remarks.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            {/* Title */}
            {(titleStatus || titleState) && (
              <div className="cr-panel-section">
                <h4 className="cr-panel-heading">Title</h4>
                <div className="cr-panel-kv">
                  <div className="cr-panel-kv-row">
                    <span className="cr-panel-kv-label">TITLE STATE</span>
                    <span className="cr-panel-kv-value">{titleState || "--"}</span>
                  </div>
                  <div className="cr-panel-kv-row">
                    <span className="cr-panel-kv-label">TITLE STATUS</span>
                    <span className="cr-panel-kv-value">{titleStatus || "NOT SPECIFIED"}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Issues Summary */}
            {granularInspection && (
              <div className="cr-panel-section">
                <h4 className="cr-panel-heading">Issues</h4>
                <div className="cr-issues-table">
                  {GRANULAR_SECTION_ORDER.map((sectionId) => {
                    const section = granularInspection[sectionId];
                    if (!section) return null;
                    const count = section.issue_count;
                    return (
                      <div key={sectionId} className="cr-issues-row">
                        <span className="cr-issues-label">{section.label}</span>
                        <span className={`cr-issues-count${count > 0 ? " cr-issues-count-alert" : ""}`}>{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── INSPECTION HEADER BAR ── */}
        {granularInspection && <div className="cr-inspection-banner">INSPECTION</div>}

        {/* ── GRANULAR INSPECTION SECTIONS ── */}
        {granularInspection && GRANULAR_SECTION_ORDER.map((sectionId) => {
          const section = granularInspection[sectionId];
          if (!section) return null;
          const open = isSectionOpen(`granular-${sectionId}`, Boolean(section.issue_count));
          return (
            <section key={sectionId} className="cr-section">
              <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection(`granular-${sectionId}`)} aria-expanded={open}>
                <span className="cr-section-title">
                  {renderSectionIcon(sectionId)}
                  {section.label}
                  {section.issue_count > 0 && <span className="cr-section-issue-pill">{section.issue_count}</span>}
                </span>
                <FaChevronDown className={`cr-section-chevron${open ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
              </button>
              {open && renderGranularSectionBody(section)}
            </section>
          );
        })}

        {/* ── TITLE & VEHICLE HISTORY (AutoCheck integrated) ── */}
        <section className="cr-section">
          <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection("title-history")} aria-expanded={isSectionOpen("title-history", true)}>
            <span className="cr-section-title"><FaFileLines aria-hidden="true" /> TITLE &amp; VEHICLE HISTORY</span>
            <FaChevronDown className={`cr-section-chevron${isSectionOpen("title-history", true) ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
          </button>
          {isSectionOpen("title-history", true) && <div className="cr-title-history-content">
            {/* Title info row */}
            <div className="cr-inspection-grid" style={{ marginBottom: 16 }}>
              <div className="cr-field-cell">
                <span className="cr-field-label">Title State</span>
                <span className="cr-field-value">{titleState || "--"}</span>
              </div>
              <div className="cr-field-cell">
                <span className="cr-field-label">Title Status</span>
                <span className="cr-field-value">{titleStatus || "Not Specified"}</span>
              </div>
              {titleBranding && (
                <div className="cr-field-cell">
                  <span className="cr-field-label">Title Branding</span>
                  <span className="cr-field-value">{titleBranding}</span>
                </div>
              )}
              {vehicleHistory?.owners != null && (
                <div className="cr-field-cell">
                  <span className="cr-field-label">Owners</span>
                  <span className="cr-field-value">{vehicleHistory.owners}</span>
                </div>
              )}
              {vehicleHistory?.accidents != null && (
                <div className={`cr-field-cell${vehicleHistory.accidents > 0 ? " cr-field-issue" : ""}`}>
                  <span className="cr-field-label">Accidents</span>
                  <span className="cr-field-value">{vehicleHistory.accidents}</span>
                </div>
              )}
            </div>

            {/* AutoCheck */}
            {autocheck && autocheck.scrape_status !== "failed" && (
              <div className="cr-autocheck-wrap">
                <div className="cr-autocheck-hero">
                  <article className="cr-autocheck-vehicle-card">
                    <h4 className="cr-autocheck-vehicle-title">
                      {vehicle.year} {vehicle.make} {vehicle.model}{vehicle.trim ? ` ${vehicle.trim}` : ""}
                    </h4>
                    {(vehicle.body_type || vehicleInfo.engine || vehicle.fuel_type) && (
                      <p className="cr-autocheck-vehicle-subtitle">
                        {[vehicle.body_type, vehicleInfo.engine, vehicle.fuel_type].filter(Boolean).join(" ")}
                      </p>
                    )}
                    <p className="cr-autocheck-vin">VIN: {maskVin(vehicle.vin, authorized || canRevealVin)}</p>
                    <dl className="cr-autocheck-facts">
                      {renderAutoCheckFact("No. of Historical Events", autocheck.historical_event_count)}
                      {renderAutoCheckFact("Calculated Owners", autocheck.owner_count)}
                      {renderAutoCheckFact("Number of Accidents", autocheck.accident_count)}
                    </dl>
                    {(autocheck.last_reported_event_date || autocheck.last_reported_mileage != null || autocheck.attempted_at) && (
                      <div className="cr-autocheck-reported">
                        {autocheck.last_reported_event_date && (
                          <p>Last Reported Event Date: {formatAutoCheckDate(autocheck.last_reported_event_date)}</p>
                        )}
                        {autocheck.last_reported_mileage != null && (
                          <p>Last Reported Mileage: {fmtMiles(autocheck.last_reported_mileage)}</p>
                        )}
                        {!autocheck.last_reported_event_date && autocheck.attempted_at && (
                          <p>AutoCheck Captured: {formatTimestamp(autocheck.attempted_at)}</p>
                        )}
                      </div>
                    )}
                  </article>

                  <article className="cr-autocheck-score-card">
                    {autocheck.autocheck_score != null ? (
                      <>
                        {renderAutoCheckScoreGauge(autocheck.autocheck_score, autoCheckSummary.scoreRangeLow, autoCheckSummary.scoreRangeHigh)}
                        <p className="cr-autocheck-score-heading">This vehicle&apos;s AutoCheck Score: {autocheck.autocheck_score}</p>
                        <p className="cr-autocheck-score-copy">
                          Other comparable {vehicle.year} vehicles{(autocheck.score_range_label || vehicle.body_type) ? <> in the <strong>{autocheck.score_range_label || vehicle.body_type}</strong></> : ""} typically
                          score between <strong>{autoCheckSummary.scoreRangeLow}-{autoCheckSummary.scoreRangeHigh}</strong>.
                        </p>
                        {autocheck.view_report_href && (
                          <button className="cr-autocheck-learn" onClick={() => window.open(autocheck.view_report_href!, "_blank", "noopener,noreferrer")}>
                            Learn more about the AutoCheck Score
                          </button>
                        )}
                      </>
                    ) : (
                      <p className="cr-comments">AutoCheck score not provided for this vehicle.</p>
                    )}
                  </article>
                </div>

                <div className="cr-autocheck-carfax">
                  <span className="cr-autocheck-carfax-icon" aria-hidden="true" />
                  <span className="cr-autocheck-carfax-copy">
                    Show me the{" "}
                    {autocheck.report_logo_url ? (
                      <button className="cr-autocheck-logo-button" onClick={() => openExternal(getCarfaxHref(vehicle.vin))} aria-label="Open CARFAX report">
                        <img src={autocheck.report_logo_url} alt="Vehicle history report" />
                      </button>
                    ) : (
                      <button className="cr-autocheck-logo-button cr-autocheck-logo-text" onClick={() => openExternal(getCarfaxHref(vehicle.vin))} aria-label="Open CARFAX report">
                        <strong>CARFAX</strong>
                      </button>
                    )}
                  </span>
                  <button className="cr-autocheck-carfax-button" onClick={() => openExternal(getCarfaxHref(vehicle.vin))}>
                    View now
                  </button>
                </div>

                <div className="cr-autocheck-check-list">
                  {renderAutoCheckCheck("titleBrand", "Major State Title Brand Check", autocheck.title_brand_check, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("accident", "Accident Check", autocheck.accident_check, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("damage", "Damage Check", autocheck.damage_check, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("odometer", "Odometer Check", autocheck.odometer_check, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("otherTitleEvent", "Other Title Brand and Specific Event Check", autocheck.other_title_brand_event_check, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("vehicleUse", "Vehicle Usage Check", autocheck.vehicle_use, setAutoCheckInfoKey)}
                  {renderAutoCheckCheck("buyback", "AutoCheck Buyback Protection", autocheck.buyback_protection, setAutoCheckInfoKey)}
                </div>

                {(autocheck.full_report_text || autocheck.view_report_href) && (
                  <details className="cr-autocheck-details">
                    <summary>
                      <span>Full AutoCheck Report</span>
                      <span className="cr-autocheck-details-hint">Expand</span>
                    </summary>
                    <div className="cr-autocheck-details-body">
                      {isAdmin && autocheck.view_report_href && (
                        <div className="cr-autocheck-report-actions">
                          <button className="button" onClick={() => window.open(autocheck.view_report_href!, "_blank", "noopener,noreferrer")}>
                            Open AutoCheck Source
                          </button>
                        </div>
                      )}
                      {autocheck.full_report_text ? (
                        <pre className="cr-autocheck-report-text">{autocheck.full_report_text}</pre>
                      ) : (
                        <p className="cr-comments">No report transcript was provided with this scrape.</p>
                      )}
                    </div>
                  </details>
                )}
              </div>
            )}

            {autocheck?.scrape_status === "failed" && (
              <div className="cr-autocheck-unavailable">
                <div>
                  <strong>AutoCheck data temporarily unavailable</strong>
                  <p>
                    {autocheck.failure_message ||
                      "We could not retrieve the Experian AutoCheck history on this pass. The rest of the inspection report is still available."}
                  </p>
                </div>
                {autocheck.attempted_at && (
                  <span className="cr-autocheck-attempted">Attempted {formatTimestamp(autocheck.attempted_at)}</span>
                )}
              </div>
            )}
          </div>}
        </section>

        {/* ── INSPECTION QUESTIONNAIRE ── */}
        {problemHighlights.length > 0 && (
          <section className="cr-section">
            <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection("problem-highlights")} aria-expanded={isSectionOpen("problem-highlights", true)}>
              <span className="cr-section-title"><FaTriangleExclamation aria-hidden="true" /> INSPECTION QUESTIONNAIRE</span>
              <FaChevronDown className={`cr-section-chevron${isSectionOpen("problem-highlights", true) ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
            </button>
            {isSectionOpen("problem-highlights", true) && (
              <ul className="cr-announce-list cr-problem-list">
                {problemHighlights.map((h, i) => <li key={i}>{h}</li>)}
              </ul>
            )}
          </section>
        )}

        {/* ── EQUIPMENT / FEATURES ── */}
        {equipmentSection.items.length > 0 && (
          <section className="cr-section">
            <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection("equipment")} aria-expanded={isSectionOpen("equipment", false)}>
              <span className="cr-section-title"><FaListCheck aria-hidden="true" /> {equipmentSection.title}</span>
              <FaChevronDown className={`cr-section-chevron${isSectionOpen("equipment", false) ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
            </button>
            {isSectionOpen("equipment", false) && (
              <div className="cr-equipment-wrap">
                {equipmentSection.subtitle && <p className="cr-comments">{equipmentSection.subtitle}</p>}
                <div className="cr-equipment-grid">
                  {equipmentSection.items.map((item) => (
                    <div key={item.key} className="cr-equipment-card">
                      <strong className="cr-equipment-title">{item.title}</strong>
                      {item.meta && <span className="cr-equipment-meta">{item.meta}</span>}
                      {item.detail && <span className="cr-equipment-detail">{item.detail}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* ── DAMAGE REPORT ── */}
        {damageItems.length > 0 && (
          <section className="cr-section">
            <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection("damage")} aria-expanded={isSectionOpen("damage", true)}>
              <span className="cr-section-title">
                <FaTriangleExclamation aria-hidden="true" /> DAMAGE REPORT
                {damageSummary && <span className="cr-damage-count">{damageSummary.total_items ?? damageItems.length} item{(damageSummary.total_items ?? damageItems.length) !== 1 ? "s" : ""}</span>}
                {damageSummary?.structural_issue && <span className="cr-structural-flag">STRUCTURAL ISSUE</span>}
              </span>
              <FaChevronDown className={`cr-section-chevron${isSectionOpen("damage", true) ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
            </button>
            {isSectionOpen("damage", true) && (
              <>
                <table className="cr-damage-table">
                  <thead>
                    <tr><th>Location</th><th>Damage Type</th><th>Severity</th><th>Description</th><th>Pics</th></tr>
                  </thead>
                  <tbody>
                    {damageItems.map((d, i) => {
                      const photoUrls = getDamagePhotoUrls(d);
                      return (
                        <tr key={i}>
                          <td>{getDamageLocation(d)}</td>
                          <td>{getDamageType(d)}</td>
                          <td>
                            <span className={`cr-severity cr-severity-${getDamageSeverityColor(d)}`}>
                              {getDamageSeverity(d)}
                            </span>
                          </td>
                          <td>{getDamageDescription(d)}</td>
                          <td>
                            {photoUrls.length > 0 ? (
                              <button className="cr-damage-photo-button" onClick={() => openExternal(photoUrls[0])}>
                                View {photoUrls.length > 1 ? photoUrls.length : ""}
                              </button>
                            ) : "\u2014"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {severitySummary && <p className="cr-comments" style={{ fontSize: 13, color: "var(--muted)" }}>{severitySummary}</p>}
              </>
            )}
          </section>
        )}

        {/* ── VEHICLE NOTES ── */}
        <section className="cr-section">
          <button className="cr-section-bar cr-section-toggle" onClick={() => toggleSection("vehicle-notes")} aria-expanded={isSectionOpen("vehicle-notes", false)}>
            <span className="cr-section-title"><FaFileLines aria-hidden="true" /> VEHICLE NOTES</span>
            <FaChevronDown className={`cr-section-chevron${isSectionOpen("vehicle-notes", false) ? " cr-section-chevron-open" : ""}`} aria-hidden="true" />
          </button>
          {isSectionOpen("vehicle-notes", false) && (
            sellerCommentsItems.length > 0 ? (
              <ul className="cr-announce-list">
                {sellerCommentsItems.map((c, i) => <li key={i}>{sanitizePublicText(c)}</li>)}
              </ul>
            ) : (
              <p className="cr-comments">{sanitizePublicText(vehicle.seller_comments || "") || "No comments provided."}</p>
            )
          )}
        </section>

        {/* ── ADDITIONAL IMAGES ── */}
        {categorizedImages.length > 20 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">ADDITIONAL IMAGES</h3>
            <div className="cr-image-grid">
              {categorizedImages.slice(20).map((img, i) => (
                <div key={i} className="cr-grid-thumb" onClick={() => { setActiveCategory("all"); setGalleryIndex(20 + i); setLightboxOpen(true); }}>
                  <img src={img.url} alt={`Image ${i + 21}`} onError={(e) => { e.currentTarget.src = FALLBACK_IMAGE; }} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── ORIGINAL CR BUTTON (admin only) ── */}
        {isAdmin && crUrl && (
          <section className="cr-section" style={{ textAlign: "center", padding: "20px 0" }}>
            <button className="button" onClick={() => window.open(crUrl, "_blank", "noopener,noreferrer")} style={{ fontSize: 16, padding: "12px 32px" }}>
              See Original Inspection Report
            </button>
          </section>
        )}
      </main>

      {activeAutoCheckInfo && (
        <div className="cr-info-modal-backdrop" onClick={() => setAutoCheckInfoKey(null)}>
          <section
            className="cr-info-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cr-autocheck-info-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="cr-info-modal-close"
              aria-label="Close AutoCheck information"
              onClick={() => setAutoCheckInfoKey(null)}
            >
              &times;
            </button>
            <span className="cr-info-modal-eyebrow">AutoCheck Reference</span>
            <h3 id="cr-autocheck-info-title">{activeAutoCheckInfo.title}</h3>
            {activeAutoCheckInfo.body.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </section>
        </div>
      )}

      {/* ── LIGHTBOX MODAL (fullscreen overlay with arrows) ── */}
      {lightboxOpen && (
        <div className="cr-overlay" onClick={() => setLightboxOpen(false)}>
          {/* Close button */}
          <button className="cr-overlay-close" onClick={() => setLightboxOpen(false)}>&times;</button>

          {/* Counter */}
          <div className="cr-overlay-counter">
            {filteredImages.length > 0 ? `${galleryIndex + 1} / ${filteredImages.length}` : ""}
          </div>

          {/* Left arrow */}
          {filteredImages.length > 1 && (
            <button
              className="cr-overlay-arrow cr-overlay-arrow-left"
              onClick={(e) => { e.stopPropagation(); navigateGallery(-1); }}
              aria-label="Previous"
            >
              &lsaquo;
            </button>
          )}

          {/* Main image */}
          <img
            src={currentImage}
            alt="Full size"
            className="cr-overlay-img"
            onClick={(e) => e.stopPropagation()}
            onError={(e) => { e.currentTarget.src = FALLBACK_IMAGE; }}
          />

          {/* Right arrow */}
          {filteredImages.length > 1 && (
            <button
              className="cr-overlay-arrow cr-overlay-arrow-right"
              onClick={(e) => { e.stopPropagation(); navigateGallery(1); }}
              aria-label="Next"
            >
              &rsaquo;
            </button>
          )}

          {/* Thumbnail strip at bottom */}
          <div className="cr-overlay-thumbstrip" onClick={(e) => e.stopPropagation()}>
            {filteredImages.map((img, i) => (
              <div
                key={i}
                className={`cr-gallery-thumb${i === galleryIndex ? " cr-gallery-thumb-active" : ""}`}
                onClick={() => setGalleryIndex(i)}
              >
                <img src={img.url} alt={`Thumb ${i + 1}`} onError={(e) => { e.currentTarget.src = FALLBACK_IMAGE; }} />
              </div>
            ))}
          </div>
        </div>
      )}

      <style jsx>{`
        /* ── Layout ── */
        .cr-doc { max-width: 1200px; margin: 0 auto; overflow-wrap: anywhere; word-break: break-word; }

        .cr-doc-header { background: var(--card-bg, #1a1a2e); padding: 16px 20px; border-radius: 8px; margin-bottom: 12px; }
        .cr-doc-header-inner { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .cr-doc-brand { margin: 0; font-size: 20px; }
        .cr-doc-header-actions { display: flex; gap: 8px; flex-wrap: wrap; }

        /* ── Vehicle Title Bar ── */
        .cr-vehicle-title-bar { padding: 16px 20px; border-bottom: 2px solid #c9a44a; margin-bottom: 12px; }
        .cr-vehicle-name { margin: 0; font-size: 22px; font-weight: 700; color: #e8e8e8; }
        .cr-vehicle-specs { display: flex; flex-wrap: wrap; gap: 6px; font-size: 13px; color: #aaa; margin-top: 4px; }
        .cr-spec-sep { color: #666; }
        .cr-vehicle-seller { font-size: 13px; font-weight: 600; text-transform: uppercase; color: #bbb; margin-top: 4px; }

        /* ── Hero Layout: Gallery + Summary Panel ── */
        .cr-hero-layout { display: grid; grid-template-columns: 1fr 340px; gap: 0; margin-bottom: 12px; border: 1px solid #333; border-radius: 8px; overflow: hidden; }

        /* ── Gallery ── */
        .cr-gallery { background: #111; }
        .cr-gallery-stage { position: relative; min-height: 380px; display: flex; align-items: center; justify-content: center; background: #0a0a0a; cursor: pointer; }
        .cr-gallery-main-img { max-width: 100%; max-height: 420px; object-fit: contain; display: block; }
        .cr-gallery-arrow {
          position: absolute; top: 50%; transform: translateY(-50%);
          background: rgba(255,255,255,0.7); border: none; color: #222;
          width: 40px; height: 40px; border-radius: 50%;
          font-size: 24px; font-weight: 700; cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          z-index: 2; transition: background 0.15s;
        }
        .cr-gallery-arrow:hover { background: rgba(255,255,255,0.95); }
        .cr-gallery-arrow-left { left: 10px; }
        .cr-gallery-arrow-right { right: 10px; }
        .cr-gallery-counter {
          position: absolute; bottom: 10px; left: 14px;
          font-size: 13px; color: #ccc; background: rgba(0,0,0,0.55);
          padding: 4px 10px; border-radius: 4px;
          display: flex; align-items: center; gap: 8px;
        }
        .cr-gallery-fullscreen { background: none; border: none; color: #ccc; font-size: 16px; cursor: pointer; padding: 0; }
        .cr-gallery-fullscreen:hover { color: #fff; }
        .cr-gallery-thumbstrip {
          display: flex; gap: 4px; padding: 6px 8px;
          overflow-x: auto; scrollbar-width: thin; background: #111;
        }
        .cr-gallery-thumb {
          flex-shrink: 0; width: 64px; height: 48px;
          border: 2px solid transparent; border-radius: 3px;
          overflow: hidden; cursor: pointer; opacity: 0.7;
          transition: opacity 0.15s, border-color 0.15s;
        }
        .cr-gallery-thumb:hover { opacity: 1; }
        .cr-gallery-thumb-active { border-color: #c9a44a; opacity: 1; }
        .cr-gallery-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .cr-gallery-tabs {
          display: flex; gap: 0; border-top: 1px solid #333; background: #181818;
        }
        .cr-gallery-tab {
          flex: 1; display: flex; align-items: center; justify-content: center; gap: 4px;
          padding: 8px 6px; background: none; border: none; border-bottom: 2px solid transparent;
          color: #aaa; font-size: 12px; font-weight: 700; cursor: pointer;
          text-transform: uppercase; letter-spacing: 0.5px; transition: color 0.15s, border-color 0.15s;
        }
        .cr-gallery-tab:hover { color: #fff; }
        .cr-gallery-tab-active { color: #c9a44a; border-bottom-color: #c9a44a; }
        .cr-gallery-tab-count {
          background: #333; padding: 1px 6px; border-radius: 8px;
          font-size: 10px; font-weight: 600; color: #ccc;
        }
        .cr-gallery-tab-active .cr-gallery-tab-count { background: rgba(201,164,74,0.25); color: #c9a44a; }

        /* ── Summary Panel ── */
        .cr-summary-panel {
          padding: 20px; background: var(--card-bg, #1a1a2e);
          display: flex; flex-direction: column; gap: 18px;
          overflow-y: auto; max-height: 600px;
        }
        .cr-grade-block { text-align: center; padding-bottom: 14px; border-bottom: 1px solid #333; }
        .cr-grade-circle {
          display: inline-flex; align-items: center; justify-content: center;
          width: 80px; height: 80px; border-radius: 50%;
          border: 3px solid #4a7c59; background: rgba(74,124,89,0.12);
        }
        .cr-grade-number { font-size: 32px; font-weight: 800; color: #4a7c59; }
        .cr-grade-label { display: block; font-size: 14px; font-weight: 700; color: #4a7c59; margin-top: 6px; }
        .cr-panel-section { }
        .cr-panel-heading { margin: 0 0 6px; font-size: 14px; font-weight: 700; color: #e0e0e0; }
        .cr-panel-list { margin: 0; padding: 0 0 0 18px; font-size: 13px; color: #ccc; }
        .cr-panel-list li { margin-bottom: 3px; }
        .cr-panel-kv { display: grid; gap: 6px; }
        .cr-panel-kv-row { display: flex; justify-content: space-between; font-size: 13px; border-bottom: 1px solid #333; padding-bottom: 4px; }
        .cr-panel-kv-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #999; letter-spacing: 0.3px; }
        .cr-panel-kv-value { font-weight: 600; color: #e0e0e0; }

        /* ── Issues Table ── */
        .cr-issues-table { display: grid; gap: 4px; }
        .cr-issues-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; padding: 4px 0; border-bottom: 1px solid #333; }
        .cr-issues-label { color: #ccc; }
        .cr-issues-count { font-weight: 700; color: #ccc; min-width: 28px; text-align: center; padding: 2px 6px; border-radius: 3px; }
        .cr-issues-count-alert { background: #e74c3c; color: #fff; }

        /* ── Inspection Banner ── */
        .cr-inspection-banner {
          background: #1a2744; color: #fff;
          padding: 10px 20px; font-size: 15px; font-weight: 800;
          text-transform: uppercase; letter-spacing: 1px;
          margin-bottom: 0;
        }

        /* ── Section bars ── */
        .cr-section { margin-bottom: 0; }
        .cr-section-bar {
          background: #2a2a3e; color: #e0e0e0;
          padding: 8px 14px; margin: 0;
          font-size: 14px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.5px;
          border-left: 4px solid #c9a44a;
        }
        .cr-section-toggle {
          width: 100%; border-top: 0; border-right: 0; border-bottom: 0;
          display: flex; align-items: center; justify-content: space-between;
          gap: 12px; text-align: left; cursor: pointer; font-family: inherit;
        }
        .cr-section-toggle:hover { background: #32324a; }
        .cr-section-title { display: inline-flex; align-items: center; gap: 10px; min-width: 0; }
        .cr-section-title svg { color: #c9a44a; flex: 0 0 auto; }
        .cr-section-chevron { color: #aab; transition: transform 0.15s ease; flex: 0 0 auto; }
        .cr-section-chevron-open { transform: rotate(180deg); }
        .cr-section-issue-pill {
          display: inline-flex; align-items: center; justify-content: center;
          min-width: 22px; height: 22px; padding: 0 7px; border-radius: 999px;
          background: #e74c3c; color: #fff; font-size: 12px; letter-spacing: 0;
        }
        .cr-granular-body { display: grid; gap: 14px; padding-top: 12px; }
        .cr-granular-group { display: grid; gap: 10px; }
        .cr-group-title {
          padding: 0 2px; color: #aab; font-size: 11px; font-weight: 800;
          text-transform: uppercase; letter-spacing: 0.7px;
        }
        .cr-field-source {
          display: block; margin-top: 5px; color: #8790ad; font-size: 11px;
          text-transform: capitalize;
        }
        .cr-field-evidence {
          display: block; margin-top: 5px; color: #d6b46a; font-size: 11px; line-height: 1.35;
        }
        .cr-tires-grid {
          display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;
        }

        /* ── Inspection Grid (3-col) ── */
        .cr-inspection-grid {
          display: grid; grid-template-columns: repeat(3, 1fr);
          gap: 12px; padding: 0;
        }
        .cr-field-cell {
          min-height: 62px; padding: 14px 16px;
          border: 1px solid #33384c; border-radius: 6px;
          background: rgba(32,34,68,0.92);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }
        .cr-field-label {
          display: block; font-size: 11px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.3px;
          color: #aaa; margin-bottom: 2px;
        }
        .cr-field-value { display: block; font-size: 14px; color: #e0e0e0; font-weight: 500; }
        .cr-field-issue {
          border-color: rgba(231,76,60,0.58);
          background: linear-gradient(180deg, rgba(82,38,54,0.82), rgba(32,34,68,0.94));
        }
        .cr-field-issue .cr-field-label { color: #ff9a8f; }
        .cr-field-issue .cr-field-value { color: #fff; font-weight: 700; }
        .cr-field-unavailable .cr-field-label { color: #666; }
        .cr-field-unavailable .cr-field-value { color: #666; font-style: italic; }

        /* ── Announcements / Comments ── */
        .cr-announce-list { padding: 12px 12px 12px 30px; margin: 0; }
        .cr-problem-list li { color: #e7a33e; }
        .cr-comments { padding: 12px 14px; margin: 0; }

        /* ── Damage table ── */
        .cr-damage-count { font-weight: 400; font-size: 12px; color: #aaa; }
        .cr-structural-flag { background: #e74c3c; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 3px; margin-left: 8px; }
        .cr-damage-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .cr-damage-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid #444; color: #aaa; font-size: 11px; text-transform: uppercase; }
        .cr-damage-table td { padding: 6px 10px; border-bottom: 1px solid #333; }
        .cr-severity { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: 600; }
        .cr-severity-green { background: #1a4d2e; color: #7c7; }
        .cr-severity-yellow { background: #4d3d0a; color: #e7a33e; }
        .cr-severity-orange { background: #4d2d0a; color: #ffb35c; }
        .cr-severity-red { background: #4d1a1a; color: #e74c3c; }
        .cr-severity-gray { background: #333; color: #aaa; }
        .cr-damage-photo-button {
          border: 1px solid #526ba9; border-radius: 4px; background: transparent;
          color: #8ea8ff; font: inherit; font-size: 12px; padding: 3px 8px; cursor: pointer;
        }
        .cr-damage-photo-button:hover { background: rgba(113,138,205,0.16); color: #c7d4ff; }

        /* ── Equipment ── */
        .cr-equipment-wrap { padding: 14px; display: grid; gap: 12px; }
        .cr-equipment-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
        .cr-equipment-card { border: 1px solid #3d3d52; border-radius: 6px; padding: 10px 12px; display: grid; gap: 4px; background: rgba(255,255,255,0.02); }
        .cr-equipment-title { font-size: 13px; color: #f1f1f1; }
        .cr-equipment-meta { font-size: 11px; color: #c9a44a; text-transform: uppercase; letter-spacing: 0.4px; }
        .cr-equipment-detail { font-size: 12px; color: #aaa; }

        /* ── Image grid ── */
        .cr-image-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px; }
        .cr-grid-thumb { border: 1px solid #444; border-radius: 3px; overflow: hidden; cursor: pointer; }
        .cr-grid-thumb:hover { border-color: #c9a44a; }
        .cr-grid-thumb img { width: 100%; height: 120px; object-fit: cover; display: block; }

        /* ── Title & History content ── */
        .cr-title-history-content { padding: 14px; }

        /* ── AutoCheck ── */
        .cr-autocheck-wrap { display: grid; gap: 14px; }
        .cr-autocheck-hero { display: grid; grid-template-columns: minmax(300px, 0.86fr) minmax(320px, 1fr); gap: 18px; }
        .cr-autocheck-vehicle-card,
        .cr-autocheck-score-card,
        .cr-autocheck-unavailable,
        .cr-autocheck-details {
          border: 1px solid rgba(113,138,205,0.5); border-radius: 16px;
          background:
            radial-gradient(circle at 18% 0%, rgba(87,112,189,0.18), transparent 32%),
            rgba(14,18,32,0.84);
          box-shadow: 0 16px 34px rgba(0,0,0,0.2);
        }
        .cr-autocheck-vehicle-card { padding: 28px 28px 24px; }
        .cr-autocheck-vehicle-title { margin: 0 0 12px; color: #f5f7ff; font-size: 28px; line-height: 1.1; }
        .cr-autocheck-vehicle-subtitle { margin: 0 0 12px; color: #7aa0ff; font-size: 19px; line-height: 1.35; }
        .cr-autocheck-vin { margin: 0 0 18px; color: #f8faff; font-size: 19px; font-weight: 800; }
        .cr-autocheck-facts { display: grid; gap: 10px; margin: 0; max-width: 360px; }
        .cr-autocheck-fact { display: grid; grid-template-columns: 1fr auto; gap: 18px; margin: 0; color: #f2f5ff; font-size: 18px; line-height: 1.25; }
        .cr-autocheck-fact dt { font-weight: 700; }
        .cr-autocheck-fact dd { margin: 0; min-width: 42px; text-align: left; }
        .cr-autocheck-reported { display: grid; gap: 12px; margin-top: 28px; padding-top: 24px; border-top: 1px solid rgba(180,190,220,0.28); color: #f1f4ff; font-size: 18px; }
        .cr-autocheck-reported p { margin: 0; }
        .cr-autocheck-score-card { padding: 22px 28px 26px; text-align: center; display: grid; align-content: start; justify-items: center; }
        .cr-autocheck-gauge { width: min(100%, 470px); height: auto; margin: -6px auto -2px; overflow: visible; }
        .cr-autocheck-gauge-track {
          fill: none; stroke: rgba(204,208,218,0.38); stroke-width: 32; stroke-linecap: butt;
          filter: drop-shadow(0 1px 0 rgba(255,255,255,0.16));
        }
        .cr-autocheck-gauge-knob {
          fill: #fbf9ff; stroke: #6b3d92; stroke-width: 7;
          filter: drop-shadow(0 4px 7px rgba(0,0,0,0.36));
        }
        .cr-autocheck-gauge-range,
        .cr-autocheck-gauge-score {
          font-family: inherit; dominant-baseline: middle; text-anchor: middle;
        }
        .cr-autocheck-gauge-range { fill: #d9dfec; font-size: 22px; font-weight: 500; }
        .cr-autocheck-gauge-score { fill: #6f8dff; font-size: 64px; font-weight: 900; }
        .cr-autocheck-score-heading { margin: 0 0 12px; color: #7395ff; font-size: 25px; font-weight: 800; }
        .cr-autocheck-score-copy { margin: 0; color: #f2f5ff; font-size: 17px; line-height: 1.45; max-width: 560px; }
        .cr-autocheck-score-copy strong { color: #fff; }
        .cr-autocheck-learn {
          margin-top: 14px; border: 0; background: transparent; color: #7aa0ff;
          font: inherit; cursor: pointer;
        }
        .cr-autocheck-learn:hover { color: #a9c1ff; }
        .cr-autocheck-carfax {
          min-height: 112px; padding: 18px 34px; border: 1px solid rgba(125,113,205,0.62); border-radius: 10px;
          display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 30px;
          background:
            radial-gradient(circle at 45% 50%, rgba(255,255,255,0.14), transparent 1px) 0 0 / 11px 11px,
            linear-gradient(105deg, #283589 0%, #5b357f 45%, #b33878 100%);
          color: #fff; overflow: hidden;
        }
        .cr-autocheck-carfax-icon {
          position: relative; width: 72px; height: 82px; border: 4px solid rgba(255,255,255,0.94); border-radius: 12px;
        }
        .cr-autocheck-carfax-icon::before {
          content: ""; position: absolute; left: 14px; top: 16px; width: 32px; height: 4px; border-radius: 999px;
          background: #fff; box-shadow: 0 12px 0 #fff, 0 24px 0 #fff, 0 36px 0 #fff;
        }
        .cr-autocheck-carfax-icon::after {
          content: ""; position: absolute; right: -16px; top: 16px; width: 24px; height: 48px;
          border-right: 7px solid #fff; border-bottom: 7px solid #fff; transform: rotate(38deg);
        }
        .cr-autocheck-carfax-copy { display: flex; align-items: center; flex-wrap: wrap; gap: 18px; font-size: 44px; font-weight: 900; line-height: 1; }
        .cr-autocheck-carfax-copy strong {
          display: inline-flex; gap: 2px; padding: 2px 7px 4px; background: #111; color: #fff;
          font-size: 35px; line-height: 1; border: 1px solid rgba(255,255,255,0.72);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.28);
        }
        .cr-autocheck-logo-button {
          display: inline-flex; align-items: center; justify-content: center;
          min-height: 44px; max-width: 260px; padding: 0; border: 0; background: transparent;
          cursor: pointer;
        }
        .cr-autocheck-logo-text { max-width: none; }
        .cr-autocheck-logo-button img { display: block; max-width: 100%; max-height: 52px; object-fit: contain; }
        .cr-autocheck-carfax-button {
          min-width: 236px; padding: 16px 28px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.82);
          background: rgba(255,255,255,0.08); color: #fff; font-size: 21px; font-weight: 800; cursor: pointer;
          text-align: center;
        }
        .cr-autocheck-carfax-button::after { content: "›"; margin-left: 46px; font-size: 26px; line-height: 0; }
        .cr-autocheck-carfax-button:hover { background: rgba(255,255,255,0.18); }
        .cr-autocheck-check-list {
          border: 1px solid rgba(113,138,205,0.76); border-radius: 18px; padding: 16px 22px;
          background: rgba(14,18,32,0.78);
        }
        .cr-autocheck-check-row {
          display: grid; grid-template-columns: 48px minmax(0, 1fr) auto; align-items: center; gap: 18px;
          min-height: 72px; border-bottom: 1px solid rgba(193,202,226,0.15);
          color: #f7f9ff; font-size: 23px;
        }
        .cr-autocheck-check-row:last-child { border-bottom: 0; }
        .cr-autocheck-check-label { min-width: 0; }
        .cr-autocheck-check-value { color: #9fe176; font-weight: 800; }
        .cr-autocheck-check-value-info { color: #6f93ff; }
        .cr-autocheck-check-value-issue { color: #ff9a8f; }
        .cr-autocheck-check-value-muted { color: #b5bfd2; }
        .cr-autocheck-check-more {
          display: inline-flex; align-items: center; justify-content: center; gap: 8px;
          padding: 8px 0; border: 0; background: transparent; color: #7da0ff;
          font: inherit; font-size: 16px; font-weight: 700; white-space: nowrap; cursor: pointer;
        }
        .cr-autocheck-check-more:hover { color: #a9c1ff; text-decoration: underline; text-underline-offset: 3px; }
        .cr-autocheck-check-more::after { content: "›"; margin-left: 18px; font-size: 24px; line-height: 0; }
        .cr-autocheck-check-icon {
          position: relative; width: 42px; height: 42px; border-radius: 50%;
          border: 2px solid rgba(255,255,255,0.72); box-shadow: inset 0 0 0 2px rgba(0,0,0,0.16), 0 2px 7px rgba(0,0,0,0.25);
        }
        .cr-autocheck-check-icon-ok { background: linear-gradient(135deg, #9dcf72, #52762e); }
        .cr-autocheck-check-icon-info,
        .cr-autocheck-check-icon-muted { background: linear-gradient(135deg, #7796df, #304b90); }
        .cr-autocheck-check-icon-issue {
          width: 0; height: 0; border-radius: 0;
          border-left: 22px solid transparent; border-right: 22px solid transparent;
          border-bottom: 40px solid #a54442; background: transparent; box-shadow: none;
        }
        .cr-autocheck-check-icon-ok::after {
          content: ""; position: absolute; left: 12px; top: 8px; width: 12px; height: 21px;
          border-right: 5px solid #fff; border-bottom: 5px solid #fff; transform: rotate(45deg);
        }
        .cr-autocheck-check-icon-info::after,
        .cr-autocheck-check-icon-muted::after {
          content: "i"; position: absolute; inset: 0; display: grid; place-items: center;
          color: #fff; font-size: 28px; font-weight: 900; font-family: Georgia, serif;
        }
        .cr-autocheck-check-icon-issue::before {
          content: "!"; position: absolute; left: -4px; top: 10px;
          color: #fff; font-size: 24px; font-weight: 900; line-height: 1;
        }
        .cr-autocheck-unavailable {
          padding: 16px; display: flex; justify-content: space-between;
          align-items: flex-start; gap: 14px;
          background: rgba(194,100,88,0.08); border-color: rgba(194,100,88,0.28);
        }
        .cr-autocheck-unavailable strong { display: block; margin-bottom: 6px; color: #f1f5ff; }
        .cr-autocheck-unavailable p { margin: 0; color: #d1d7e4; line-height: 1.6; }
        .cr-autocheck-attempted { color: #9da8c3; font-size: 12px; white-space: nowrap; }
        .cr-autocheck-details { overflow: hidden; }
        .cr-autocheck-details summary {
          list-style: none; cursor: pointer;
          display: flex; align-items: center; justify-content: space-between;
          gap: 12px; padding: 14px 16px; font-weight: 700; color: #eef2fb;
        }
        .cr-autocheck-details summary::-webkit-details-marker { display: none; }
        .cr-autocheck-details-hint { font-size: 12px; color: #97a3ba; text-transform: uppercase; letter-spacing: 0.5px; }
        .cr-autocheck-details[open] .cr-autocheck-details-hint { color: #c9a44a; }
        .cr-autocheck-details-body { border-top: 1px solid #33384c; padding: 16px; display: grid; gap: 12px; }
        .cr-autocheck-report-actions { display: flex; justify-content: flex-start; }
        .cr-autocheck-report-text {
          margin: 0; padding: 14px; border-radius: 8px;
          background: rgba(10,14,24,0.7); border: 1px solid #2f3446;
          color: #d5dceb; font-size: 12px; line-height: 1.65;
          white-space: pre-wrap;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        }

        .cr-info-modal-backdrop {
          position: fixed; inset: 0; display: grid; place-items: center;
          padding: 20px; background: rgba(4,6,18,0.76); backdrop-filter: blur(5px);
          z-index: 10002;
        }
        .cr-info-modal-card {
          position: relative; width: min(92vw, 560px); padding: 28px 30px 26px;
          border: 1px solid rgba(125,113,205,0.58); border-radius: 14px;
          background:
            linear-gradient(145deg, rgba(34,37,78,0.98), rgba(18,22,44,0.98)),
            radial-gradient(circle at top right, rgba(201,164,74,0.18), transparent 42%);
          color: #edf2ff; box-shadow: 0 24px 70px rgba(0,0,0,0.5);
        }
        .cr-info-modal-close {
          position: absolute; top: 12px; right: 14px; width: 34px; height: 34px;
          border: 0; border-radius: 50%; background: rgba(255,255,255,0.08);
          color: #fff; font-size: 25px; line-height: 1; cursor: pointer;
        }
        .cr-info-modal-close:hover { background: rgba(255,255,255,0.16); color: #d8b968; }
        .cr-info-modal-eyebrow {
          display: block; margin-bottom: 10px; color: #d8b968; font-size: 11px;
          font-weight: 900; text-transform: uppercase; letter-spacing: 0.8px;
        }
        .cr-info-modal-card h3 { margin: 0 34px 14px 0; color: #fff; font-size: 25px; line-height: 1.18; }
        .cr-info-modal-card p { margin: 0 0 12px; color: #dbe3f6; font-size: 15px; line-height: 1.6; }
        .cr-info-modal-card p:last-child { margin-bottom: 0; }

        /* ── Fullscreen Lightbox Overlay ── */
        .cr-overlay {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.95);
          display: flex; align-items: center; justify-content: center;
          z-index: 10000;
        }
        .cr-overlay-close {
          position: fixed; top: 16px; right: 24px;
          background: none; border: none; color: #fff;
          font-size: 44px; cursor: pointer; z-index: 10001;
          line-height: 1; padding: 0; opacity: 0.8;
        }
        .cr-overlay-close:hover { opacity: 1; color: #c9a44a; }
        .cr-overlay-counter {
          position: fixed; top: 20px; left: 50%;
          transform: translateX(-50%);
          color: #ccc; font-size: 14px; font-weight: 600;
          z-index: 10001;
        }
        .cr-overlay-img { max-width: 88vw; max-height: 82vh; object-fit: contain; }
        .cr-overlay-arrow {
          position: fixed; top: 50%; transform: translateY(-50%);
          background: rgba(255,255,255,0.12); border: none; color: #fff;
          width: 52px; height: 52px; border-radius: 50%;
          font-size: 32px; font-weight: 700; cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          z-index: 10001; transition: background 0.15s;
        }
        .cr-overlay-arrow:hover { background: rgba(255,255,255,0.25); }
        .cr-overlay-arrow-left { left: 20px; }
        .cr-overlay-arrow-right { right: 20px; }
        .cr-overlay-thumbstrip {
          position: fixed; bottom: 0; left: 0; right: 0;
          display: flex; gap: 4px; padding: 10px 16px;
          overflow-x: auto; scrollbar-width: thin;
          background: rgba(0,0,0,0.85); z-index: 10001;
          justify-content: center;
        }

        @media print {
          .cr-doc-header-actions, .cr-overlay, .cr-gallery-tabs, .cr-gallery-arrow { display: none !important; }
          .cr-hero-layout { grid-template-columns: 1fr 280px; }
          .cr-gallery-stage { min-height: auto; }
          .cr-inspection-grid { break-inside: avoid; }
        }

        @media (max-width: 768px) {
          .cr-hero-layout { grid-template-columns: 1fr; }
          .cr-gallery { overflow: hidden; }
          .cr-gallery-stage { min-height: unset; height: auto; max-height: 60vw; overflow: hidden; }
          .cr-gallery-main-img { max-width: 100%; max-height: 60vw; width: auto; object-fit: contain; }
          .cr-gallery-thumbstrip { padding: 4px 6px; }
          .cr-gallery-thumb { width: 48px; height: 36px; }
          .cr-gallery-tabs { flex-wrap: wrap; }
          .cr-gallery-tab { font-size: 11px; padding: 6px 8px; }
          .cr-summary-panel { max-height: none; }
          .cr-inspection-grid { grid-template-columns: 1fr; }
          .cr-tires-grid { grid-template-columns: 1fr; }
          .cr-image-grid { grid-template-columns: repeat(2, 1fr); }
          .cr-equipment-grid { grid-template-columns: 1fr; }
          .cr-autocheck-hero { grid-template-columns: 1fr; }
          .cr-autocheck-vehicle-card { padding: 22px 18px; }
          .cr-autocheck-vehicle-title { font-size: 23px; }
          .cr-autocheck-vehicle-subtitle,
          .cr-autocheck-vin,
          .cr-autocheck-fact,
          .cr-autocheck-reported { font-size: 16px; }
          .cr-autocheck-gauge-track { stroke-width: 28; }
          .cr-autocheck-gauge-knob { r: 19; stroke-width: 6; }
          .cr-autocheck-gauge-range { font-size: 20px; }
          .cr-autocheck-gauge-score { font-size: 58px; }
          .cr-autocheck-score-heading { font-size: 21px; }
          .cr-autocheck-carfax { grid-template-columns: 1fr; justify-items: start; padding: 20px; gap: 16px; }
          .cr-autocheck-carfax-copy { font-size: 34px; }
          .cr-autocheck-carfax-copy strong { font-size: 27px; }
          .cr-autocheck-carfax-button { min-width: 0; width: 100%; }
          .cr-autocheck-check-list { padding: 10px 12px; }
          .cr-autocheck-check-row { grid-template-columns: 40px minmax(0, 1fr); gap: 14px; font-size: 18px; padding: 12px 0; }
          .cr-autocheck-check-icon { width: 36px; height: 36px; }
          .cr-autocheck-check-more { grid-column: 2; justify-content: flex-start; font-size: 14px; padding: 0; }
          .cr-autocheck-unavailable { flex-direction: column; }
          .cr-info-modal-card { padding: 24px 22px; }
          .cr-overlay-arrow { width: 40px; height: 40px; font-size: 24px; }
          .cr-overlay-arrow-left { left: 8px; }
          .cr-overlay-arrow-right { right: 8px; }
        }

        /* ── Light Mode Overrides ── */
        :global(:root[data-theme="light"]) .cr-doc-header { background: var(--surface-strong); }
        :global(:root[data-theme="light"]) .cr-vehicle-name { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-vehicle-specs { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-spec-sep { color: #bbb; }
        :global(:root[data-theme="light"]) .cr-vehicle-seller { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-hero-layout { border-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-gallery { background: #f5f7fa; }
        :global(:root[data-theme="light"]) .cr-gallery-stage { background: #edf0f5; }
        :global(:root[data-theme="light"]) .cr-gallery-counter { color: #333; background: rgba(255,255,255,0.8); }
        :global(:root[data-theme="light"]) .cr-gallery-fullscreen { color: #555; }
        :global(:root[data-theme="light"]) .cr-gallery-fullscreen:hover { color: #111; }
        :global(:root[data-theme="light"]) .cr-gallery-thumbstrip { background: #f5f7fa; }
        :global(:root[data-theme="light"]) .cr-gallery-tabs { border-top-color: var(--line); background: #f9fafb; }
        :global(:root[data-theme="light"]) .cr-gallery-tab { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-gallery-tab:hover { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-gallery-tab-count { background: #e2e6ec; color: #4a5568; }
        :global(:root[data-theme="light"]) .cr-gallery-tab-active .cr-gallery-tab-count { background: rgba(201,164,74,0.2); color: #8b6914; }
        :global(:root[data-theme="light"]) .cr-summary-panel { background: var(--surface-strong); }
        :global(:root[data-theme="light"]) .cr-grade-block { border-bottom-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-panel-heading { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-panel-list { color: #334155; }
        :global(:root[data-theme="light"]) .cr-panel-kv-row { border-bottom-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-panel-kv-label { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-panel-kv-value { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-issues-row { border-bottom-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-issues-label { color: #334155; }
        :global(:root[data-theme="light"]) .cr-issues-count { color: #334155; }
        :global(:root[data-theme="light"]) .cr-inspection-banner { background: #e8edf5; color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-section-bar { background: #edf0f5; color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-section-toggle:hover { background: #e3e8f0; }
        :global(:root[data-theme="light"]) .cr-group-title { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-field-cell {
          border-color: var(--line);
          background: #f7f9fc;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
        }
        :global(:root[data-theme="light"]) .cr-field-issue {
          border-color: rgba(185,28,28,0.38);
          background: linear-gradient(180deg, #fff4f4, #f7f9fc);
        }
        :global(:root[data-theme="light"]) .cr-field-label { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-field-value { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-field-unavailable .cr-field-label { color: #aab; }
        :global(:root[data-theme="light"]) .cr-field-unavailable .cr-field-value { color: #aab; }
        :global(:root[data-theme="light"]) .cr-comments { color: #334155; }
        :global(:root[data-theme="light"]) .cr-damage-count { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-damage-table th { border-bottom-color: #ccc; color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-damage-table td { border-bottom-color: var(--line); color: #334155; }
        :global(:root[data-theme="light"]) .cr-severity-green { background: #e6f5ec; color: #276738; }
        :global(:root[data-theme="light"]) .cr-severity-yellow { background: #fef4e1; color: #7a5c10; }
        :global(:root[data-theme="light"]) .cr-severity-orange { background: #fff0df; color: #a14f0b; }
        :global(:root[data-theme="light"]) .cr-severity-red { background: #fde8e8; color: #b91c1c; }
        :global(:root[data-theme="light"]) .cr-severity-gray { background: #edf0f5; color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-equipment-card { border-color: var(--line); background: var(--surface-soft); }
        :global(:root[data-theme="light"]) .cr-equipment-title { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-equipment-detail { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-grid-thumb { border-color: #ccc; }
        :global(:root[data-theme="light"]) .cr-autocheck-vehicle-card,
        :global(:root[data-theme="light"]) .cr-autocheck-score-card,
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable,
        :global(:root[data-theme="light"]) .cr-autocheck-details {
          border-color: rgba(71,91,160,0.62);
          background: #f1f1f1;
          box-shadow: 0 14px 28px rgba(15,23,42,0.08);
        }
        :global(:root[data-theme="light"]) .cr-autocheck-vehicle-title,
        :global(:root[data-theme="light"]) .cr-autocheck-vin,
        :global(:root[data-theme="light"]) .cr-autocheck-fact,
        :global(:root[data-theme="light"]) .cr-autocheck-reported { color: #101827; }
        :global(:root[data-theme="light"]) .cr-autocheck-vehicle-subtitle { color: #3f579e; }
        :global(:root[data-theme="light"]) .cr-autocheck-score-card { background: #f1f1f1; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-track { stroke: #c9c9c9; filter: none; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-range { fill: #444; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-score { fill: #566fae; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-score,
        :global(:root[data-theme="light"]) .cr-autocheck-score-heading,
        :global(:root[data-theme="light"]) .cr-autocheck-learn { color: #566fae; }
        :global(:root[data-theme="light"]) .cr-autocheck-score-copy { color: #101827; }
        :global(:root[data-theme="light"]) .cr-autocheck-check-list { background: #fff; border-color: #7383d1; }
        :global(:root[data-theme="light"]) .cr-autocheck-check-row { color: #101827; border-bottom-color: rgba(71,91,160,0.12); }
        :global(:root[data-theme="light"]) .cr-autocheck-check-more { color: #40599f; }
        :global(:root[data-theme="light"]) .cr-info-modal-card {
          border-color: rgba(71,91,160,0.42);
          background: #fff;
          color: #101827;
        }
        :global(:root[data-theme="light"]) .cr-info-modal-card h3 { color: #101827; }
        :global(:root[data-theme="light"]) .cr-info-modal-card p { color: #334155; }
        :global(:root[data-theme="light"]) .cr-info-modal-close { background: #edf0f5; color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-attempted { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-details summary { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-details-hint { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-details-body { border-top-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-autocheck-report-text { background: #f5f7fa; border-color: var(--line); color: #334155; }
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable strong { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable p { color: #334155; }
      `}</style>

      <style jsx global>{`
        .cr-granular-body {
          display: grid;
          gap: 14px;
          padding-top: 12px;
        }
        .cr-granular-group {
          display: grid;
          gap: 10px;
        }
        .cr-group-title {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 0 2px;
          color: #aab;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.7px;
        }
        .cr-inspection-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
          padding: 0;
        }
        .cr-tires-layout {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(150px, 0.52fr) minmax(0, 1fr);
          align-items: center;
          gap: 16px;
        }
        .cr-tires-column {
          display: grid;
          gap: 12px;
        }
        .cr-tires-visual {
          display: grid;
          place-items: center;
          min-height: 330px;
        }
        .cr-tires-visual img {
          display: block;
          width: min(100%, 190px);
          height: auto;
          object-fit: contain;
          filter: drop-shadow(0 12px 24px rgba(0,0,0,0.34));
        }
        .cr-field-cell {
          min-height: 62px;
          padding: 14px 16px;
          border: 1px solid #33384c;
          border-radius: 6px;
          background: rgba(32,34,68,0.92);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }
        .cr-field-label {
          display: block;
          margin-bottom: 4px;
          color: #aaa;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }
        .cr-field-value {
          display: block;
          color: #f1f4ff;
          font-size: 14px;
          font-weight: 700;
          line-height: 1.35;
        }
        .cr-field-source {
          display: block;
          margin-top: 6px;
          color: #8790ad;
          font-size: 11px;
          text-transform: capitalize;
        }
        .cr-field-evidence {
          display: block;
          margin-top: 6px;
          color: #d6b46a;
          font-size: 11px;
          line-height: 1.35;
        }
        .cr-field-issue {
          border-color: rgba(231,76,60,0.58);
          background: linear-gradient(180deg, rgba(82,38,54,0.82), rgba(32,34,68,0.94));
        }
        .cr-field-issue .cr-field-label {
          color: #ff9a8f;
        }
        .cr-field-issue .cr-field-value {
          color: #fff;
          font-weight: 800;
        }
        .cr-field-unavailable .cr-field-label,
        .cr-field-unavailable .cr-field-value {
          color: #747a91;
          font-style: italic;
        }
        .cr-autocheck-check-row {
          display: grid;
          grid-template-columns: 48px minmax(0, 1fr);
          align-items: center;
          gap: 18px;
          min-height: 72px;
          border-bottom: 1px solid rgba(193,202,226,0.15);
          color: #f7f9ff;
          font-size: 23px;
        }
        .cr-autocheck-check-row:last-child {
          border-bottom: 0;
        }
        .cr-autocheck-check-label {
          display: flex;
          align-items: baseline;
          flex-wrap: wrap;
          gap: 0 14px;
          min-width: 0;
        }
        .cr-autocheck-check-text {
          min-width: 0;
        }
        .cr-autocheck-check-value {
          color: #9fe176;
          font-weight: 800;
        }
        .cr-autocheck-check-value-info {
          color: #6f93ff;
        }
        .cr-autocheck-check-value-issue {
          color: #ff9a8f;
        }
        .cr-autocheck-check-value-muted {
          color: #b5bfd2;
        }
        .cr-autocheck-check-more {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 0;
          padding: 0;
          border: 0;
          border-radius: 0;
          background: transparent;
          color: #7da0ff;
          box-shadow: none;
          appearance: none;
          font: inherit;
          font-size: 16px;
          font-weight: 800;
          line-height: 1.2;
          white-space: nowrap;
          cursor: pointer;
        }
        .cr-autocheck-check-more:hover,
        .cr-autocheck-check-more:focus-visible {
          color: #a9c1ff;
          text-decoration: underline;
          text-underline-offset: 3px;
          outline: none;
        }
        .cr-autocheck-check-more::after {
          content: "›";
          margin-left: 9px;
          font-size: 24px;
          line-height: 0;
        }
        .cr-autocheck-check-icon {
          position: relative;
          width: 42px;
          height: 42px;
          border: 2px solid rgba(255,255,255,0.72);
          border-radius: 50%;
          box-shadow: inset 0 0 0 2px rgba(0,0,0,0.16), 0 2px 7px rgba(0,0,0,0.25);
        }
        .cr-autocheck-check-icon-ok {
          background: linear-gradient(135deg, #9dcf72, #52762e);
        }
        .cr-autocheck-check-icon-info,
        .cr-autocheck-check-icon-muted {
          background: linear-gradient(135deg, #7796df, #304b90);
        }
        .cr-autocheck-check-icon-issue {
          width: 0;
          height: 0;
          border-right: 22px solid transparent;
          border-bottom: 40px solid #a54442;
          border-left: 22px solid transparent;
          border-radius: 0;
          background: transparent;
          box-shadow: none;
        }
        .cr-autocheck-check-icon-ok::after {
          content: "";
          position: absolute;
          left: 12px;
          top: 8px;
          width: 12px;
          height: 21px;
          border-right: 5px solid #fff;
          border-bottom: 5px solid #fff;
          transform: rotate(45deg);
        }
        .cr-autocheck-check-icon-info::after,
        .cr-autocheck-check-icon-muted::after {
          content: "i";
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          color: #fff;
          font-family: Georgia, serif;
          font-size: 28px;
          font-weight: 900;
        }
        .cr-autocheck-check-icon-issue::before {
          content: "!";
          position: absolute;
          left: -4px;
          top: 10px;
          color: #fff;
          font-size: 24px;
          font-weight: 900;
          line-height: 1;
        }
        :root[data-theme="light"] .cr-field-cell {
          border-color: var(--line);
          background: #f7f9fc;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
        }
        :root[data-theme="light"] .cr-field-issue {
          border-color: rgba(185,28,28,0.38);
          background: linear-gradient(180deg, #fff4f4, #f7f9fc);
        }
        :root[data-theme="light"] .cr-field-label,
        :root[data-theme="light"] .cr-group-title {
          color: var(--muted);
        }
        :root[data-theme="light"] .cr-field-value,
        :root[data-theme="light"] .cr-autocheck-check-row {
          color: #101827;
        }
        :root[data-theme="light"] .cr-autocheck-check-more {
          color: #40599f;
        }
        @media (max-width: 768px) {
          .cr-inspection-grid {
            grid-template-columns: 1fr;
          }
          .cr-tires-layout {
            grid-template-columns: 1fr;
          }
          .cr-tires-visual {
            order: -1;
            min-height: 190px;
          }
          .cr-tires-visual img {
            width: min(60%, 150px);
          }
          .cr-autocheck-check-row {
            grid-template-columns: 40px minmax(0, 1fr);
            gap: 14px;
            padding: 12px 0;
            font-size: 18px;
          }
          .cr-autocheck-check-icon {
            width: 36px;
            height: 36px;
          }
          .cr-autocheck-check-more {
            font-size: 14px;
          }
        }
      `}</style>
    </>
  );
}

/* ── Helpers ── */

function renderAutoCheckFact(label: string, value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="cr-autocheck-fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function renderAutoCheckScoreGauge(score: number, rangeLow: number, rangeHigh: number) {
  const low = clampScore(rangeLow);
  const high = clampScore(Math.max(rangeHigh, low + 1));
  const position = Math.max(0, Math.min(1, (score - low) / Math.max(1, high - low)));
  const cx = 160;
  const cy = 150;
  const radius = 106;
  const angle = Math.PI - Math.PI * position;
  const knobX = cx + radius * Math.cos(angle);
  const knobY = cy - radius * Math.sin(angle);

  return (
    <svg className="cr-autocheck-gauge" viewBox="0 0 320 205" role="img" aria-label={`AutoCheck score ${score}, range ${low} to ${high}`}>
      <path className="cr-autocheck-gauge-track" d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`} fill="none" stroke="rgba(204,208,218,0.38)" strokeWidth="32" />
      <circle className="cr-autocheck-gauge-knob" cx={knobX} cy={knobY} r="23" fill="#fbf9ff" stroke="#6b3d92" strokeWidth="7" />
      <text className="cr-autocheck-gauge-range" x="36" y="126" fill="#d9dfec">{low}</text>
      <text className="cr-autocheck-gauge-range" x="284" y="126" fill="#d9dfec">{high}</text>
      <text className="cr-autocheck-gauge-score" x={cx} y="132" fill="#6f8dff">{score}</text>
    </svg>
  );
}

function renderAutoCheckCheck(
  infoKey: AutoCheckInfoKey,
  label: string,
  value: string | null | undefined,
  onInfoClick: (key: AutoCheckInfoKey) => void,
) {
  if (!value) return null;
  const tone = classifyAutoCheckValue(value);
  const displayValue = formatAutoCheckCheckValue(value, tone);
  return (
    <div className="cr-autocheck-check-row">
      <span className={`cr-autocheck-check-icon cr-autocheck-check-icon-${tone}`} aria-hidden="true" />
      <span className="cr-autocheck-check-label">
        <span className="cr-autocheck-check-text">
          {label} - <strong className={`cr-autocheck-check-value cr-autocheck-check-value-${tone}`}>{displayValue}</strong>
        </span>
        <button type="button" className="cr-autocheck-check-more" onClick={() => onInfoClick(infoKey)}>
          More info
        </button>
      </span>
    </div>
  );
}

function renderSectionIcon(sectionId: string) {
  if (sectionId === "drivability") return <FaCar aria-hidden="true" />;
  if (sectionId === "mechanical") return <FaWrench aria-hidden="true" />;
  if (sectionId === "tires") return <FaCircleDot aria-hidden="true" />;
  if (sectionId === "exterior") return <FaCar aria-hidden="true" />;
  if (sectionId === "interior") return <FaGaugeHigh aria-hidden="true" />;
  return <FaListCheck aria-hidden="true" />;
}

function renderGranularSectionBody(section: GranularSection) {
  const fields = Object.entries(section.fields || {});
  if (section.label === "Tires & Wheels") {
    return renderTiresSectionBody(fields);
  }

  const grouped = new Map<string, Array<[string, GranularField]>>();
  const groupLabels = section.groups || {};
  for (const entry of fields) {
    const groupId = entry[1].group || "default";
    if (!grouped.has(groupId)) grouped.set(groupId, []);
    grouped.get(groupId)!.push(entry);
  }

  return (
    <div className="cr-granular-body">
      {Array.from(grouped.entries()).map(([groupId, groupFields]) => (
        <div className="cr-granular-group" key={groupId}>
          {groupId !== "default" && <div className="cr-group-title">{groupLabels[groupId] || labelize(groupId)}</div>}
          <div className="cr-inspection-grid">
            {groupFields.map(([fieldId, field]) => renderGranularField(fieldId, field))}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderTiresSectionBody(fields: Array<[string, GranularField]>) {
  const left = fields.filter(([, field]) => field.label.toLowerCase().startsWith("driver"));
  const right = fields.filter(([, field]) => field.label.toLowerCase().startsWith("passenger"));
  const uncategorized = fields.filter(([, field]) => {
    const label = field.label.toLowerCase();
    return !label.startsWith("driver") && !label.startsWith("passenger");
  });

  const leftFields = left.length || right.length ? [...left, ...uncategorized] : fields.slice(0, Math.ceil(fields.length / 2));
  const rightFields = left.length || right.length ? right : fields.slice(Math.ceil(fields.length / 2));

  return (
    <div className="cr-granular-body cr-tires-body">
      <div className="cr-tires-layout">
        <div className="cr-tires-column">
          {leftFields.map(([fieldId, field]) => renderGranularField(fieldId, field))}
        </div>
        <div className="cr-tires-visual" aria-hidden="true">
          <img src={TIRES_ICON_IMAGE} alt="" />
        </div>
        <div className="cr-tires-column">
          {rightFields.map(([fieldId, field]) => renderGranularField(fieldId, field))}
        </div>
      </div>
    </div>
  );
}

function renderGranularField(fieldId: string, field: GranularField) {
  const cls = field.status === "issue" ? " cr-field-issue" : field.status === "unknown" ? " cr-field-unavailable" : "";
  const evidence = Array.isArray(field.evidence) ? field.evidence.filter(Boolean).slice(0, 2) : [];
  return (
    <div key={fieldId} className={`cr-field-cell cr-granular-field${cls}`}>
      <span className="cr-field-label">{field.label}</span>
      <span className="cr-field-value">{field.value}</span>
      {field.source && field.source !== "default" && (
        <span className="cr-field-source">
          {field.source.replace(/_/g, " ")}
        </span>
      )}
      {evidence.length > 0 && (
        <span className="cr-field-evidence">{evidence.join("; ")}</span>
      )}
    </div>
  );
}

function buildGranularInspectionFallback(report: Record<string, unknown>, inspection: Inspection | null): GranularInspection | null {
  const existing = report.granular_inspection;
  if (existing && typeof existing === "object") return existing as GranularInspection;
  if (!inspection) return null;
  const sections: GranularInspection = {};
  for (const [sectionId, section] of Object.entries(inspection)) {
    sections[sectionId] = {
      label: section.label,
      issue_count: section.issue_count,
      fields: Object.fromEntries(
        Object.entries(section.fields).map(([fieldId, field]) => [
          fieldId,
          {
            label: field.label,
            status: field.has_issue ? "issue" : "normal",
            value: field.has_issue ? field.value : normalizeCleanInspectionValue(sectionId, field.value),
            source: field.is_default ? "default" : "inspection",
            confidence: field.is_default ? 1 : 0.9,
            evidence: field.has_issue ? [field.value] : [],
            image_refs: [],
          } satisfies GranularField,
        ]),
      ),
    };
  }
  return sections;
}

function normalizeCleanInspectionValue(sectionId: string, value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "not inspected" || normalized === "not specified" || normalized === "not available") {
    if (sectionId === "exterior" || sectionId === "interior") return "Normal - No Damage Reported";
    return "Normal - No Issue Reported";
  }
  return value;
}

function labelize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function filterVisibleInspection(inspection: Inspection | null): Inspection | null {
  if (!inspection) return null;
  const filtered: Inspection = {};
  for (const [sectionId, section] of Object.entries(inspection)) {
    const visibleFields = Object.entries(section.fields || {})
      .filter(([, field]) => !isGeneratedInspectionDefault(field));
    if (visibleFields.length === 0) continue;
    const fields = Object.fromEntries(visibleFields) as Record<string, InspectionField>;
    filtered[sectionId] = {
      ...section,
      fields,
      issue_count: Object.values(fields).filter((field) => field.has_issue).length,
    };
  }
  return Object.keys(filtered).length > 0 ? filtered : null;
}

function isGeneratedInspectionDefault(field: InspectionField): boolean {
  const normalized = field.value.trim().toLowerCase();
  if (field.is_default === false) return false;
  if (field.is_default === true) return normalized === "not inspected" || normalized === "not specified";
  return normalized === "not inspected" || normalized === "not specified";
}

function getDamageLocation(item: DamageItem): string {
  return firstText(item.location, item.section_label, item.section, item.panel) || "\u2014";
}

function getDamageType(item: DamageItem): string {
  return firstText(item.damage_type, item.damageType, item.condition, item.type) || "\u2014";
}

function getDamageSeverity(item: DamageItem): string {
  return firstText(item.reported_severity, item.severity, item.severity_label, item.severityLabel) || "\u2014";
}

function getDamageSeverityColor(item: DamageItem): string {
  const explicit = firstText(item.severity_color, item.severityColor);
  if (explicit) return explicit.toLowerCase();
  const severity = getDamageSeverity(item).toLowerCase();
  if (severity.includes("required") || severity.includes("major") || severity.includes("severe")) return "red";
  if (severity.includes("moderate")) return "yellow";
  if (severity.includes("minor") || severity.includes("normal")) return "green";
  return "gray";
}

function getDamageDescription(item: DamageItem): string {
  return firstText(item.description, item.damage_description, item.damageDescription, item.notes, item.comment) || "\u2014";
}

function getDamagePhotoUrls(item: DamageItem): string[] {
  const buckets = [item.pics, item.photos, item.pictures, item.images, item.image_urls, item.imageUrls, item.photo_urls, item.photoUrls];
  const urls: string[] = [];
  for (const bucket of buckets) {
    if (typeof bucket === "string" && bucket.startsWith("http")) {
      urls.push(bucket);
    } else if (Array.isArray(bucket)) {
      for (const entry of bucket) {
        if (typeof entry === "string" && entry.startsWith("http")) urls.push(entry);
        if (entry && typeof entry === "object") {
          const url = firstText((entry as Record<string, unknown>).url, (entry as Record<string, unknown>).href);
          if (url && url.startsWith("http")) urls.push(url);
        }
      }
    }
  }
  return Array.from(new Set(urls));
}

function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return null;
}

function getCarfaxHref(vin: string): string {
  return `${CARFAX_PARTNER_URL}?partner=${CARFAX_PARTNER_ID}&vin=${encodeURIComponent(vin)}`;
}

function openExternal(url: string) {
  window.open(url, "_blank", "noopener,noreferrer");
}

function stripSizeParam(url: string): string {
  try {
    const u = new URL(url);
    u.searchParams.delete("size");
    const cleaned = u.toString().replace(/\?size=[^&]*&?/, "?").replace(/\?$/, "");
    return cleaned;
  } catch {
    return url.replace(/\?size=[^&]*/g, "");
  }
}

function categorizeImage(url: string, role?: string): string {
  if (role === "disclosure") return "dmg";
  const lower = (url || "").toLowerCase();
  if (/interior|dash|cargo|seat|console|steering/i.test(lower)) return "int";
  if (/damage|scratch|dent|crack|chip/i.test(lower)) return "dmg";
  if (/front|rear|driver|passenger|wheel|bumper|fender|hood|trunk|roof|exterior/i.test(lower)) return "ext";
  if (/odo|vin|sticker|plate|engine.*bay/i.test(lower)) return "misc";
  return "ext"; // default to exterior for uncategorized CR photos
}

function resolveCategorizedImages(vehicle: VehicleDetail | null): CategorizedImage[] {
  if (!vehicle) return [];

  const oveImages = vehicle.ove_detail?.images || [];
  if (oveImages.length > 0) {
    const seen = new Set<string>();
    const result: CategorizedImage[] = [];
    for (const entry of oveImages) {
      const isObj = typeof entry !== "string";
      const raw = isObj ? (entry as { url?: string }).url : entry;
      if (!raw || typeof raw !== "string") continue;
      const lower = raw.toLowerCase();
      if (lower.includes(".svg") || lower.includes(".gif")) continue;
      if (lower.includes("ready_logistics.png")) continue;
      const clean = stripSizeParam(raw);
      if (seen.has(clean)) continue;
      seen.add(clean);

      const category = isObj && (entry as { category?: string }).category
        ? (entry as { category: string }).category
        : categorizeImage(clean, isObj ? (entry as { role?: string }).role : undefined);

      result.push({ url: clean, category, role: isObj ? (entry as { role?: string }).role : undefined });
    }
    if (result.length > 0) return result;
  }

  // Fallback
  const fallback =
    vehicle.display_context?.gallery_images ||
    vehicle.display_images ||
    vehicle.images ||
    [];
  return fallback.map((url) => ({ url, category: categorizeImage(url) }));
}

function parseAnnouncements(report: Record<string, unknown>, crMetadata: Record<string, unknown>): string[] {
  const MAX_ITEM_CHARS = 400;
  const sanitize = (items: unknown[]): string[] =>
    items
      .map((item) => (typeof item === "string" ? item.trim() : ""))
      .filter((item) => item.length > 0 && item.length <= MAX_ITEM_CHARS);

  const fromField = Array.isArray(report.announcements) ? sanitize(report.announcements as unknown[]) : [];
  if (fromField.length > 0) return fromField;

  const metaEnrichment = (crMetadata.announcementsEnrichment as Record<string, unknown> | undefined)?.announcements;
  if (Array.isArray(metaEnrichment)) {
    const items = sanitize(metaEnrichment);
    if (items.length > 0) return items;
  }

  const rawText = typeof report.raw_text === "string" ? report.raw_text : "";
  if (!rawText) return [];

  const jsonStart = rawText.indexOf("{");
  if (jsonStart >= 0 && jsonStart <= 32) {
    try {
      const parsed = JSON.parse(rawText.slice(jsonStart));
      const enrichment = parsed?.announcementsEnrichment?.announcements;
      if (Array.isArray(enrichment)) {
        const items = sanitize(enrichment);
        if (items.length > 0) return items;
      }
      const direct = parsed?.announcements;
      if (Array.isArray(direct)) {
        const items = sanitize(direct);
        if (items.length > 0) return items;
      }
    } catch {
      // fall through
    }
    return [];
  }

  const annoMatch = rawText.match(/Announcements\s*(.*?)(?:Remarks|Seller Comments|$)/si);
  if (annoMatch && annoMatch[1]) {
    const text = annoMatch[1].replace(/No Announcements Present/gi, "").trim();
    if (text && text !== "No" && text.length <= MAX_ITEM_CHARS) return [text];
  }
  return [];
}

function buildLegacyInspection(report: Record<string, unknown>): Inspection | null {
  const CLEAN_VALUES = new Set([
    "no issues", "none", "no damage", "not inspected", "not specified",
    "fully functional", "no oil sludge", "factory equipment installed",
    "not applicable", "n/a", "", "not available",
    "yes - starts", "yes - drives", "yes",
    "no codes found", "no codes",
  ]);

  function isIssue(value: string): boolean {
    const normalized = value.trim().toLowerCase();
    if (CLEAN_VALUES.has(normalized)) return false;
    // Numeric key counts (e.g. "1", "2", "0") are informational
    if (/^\d+$/.test(normalized)) return false;
    // Tire depth readings like '6/32" or Above' are not issues
    if (normalized.includes("/32")) return false;
    return true;
  }

  function makeField(label: string, value: string): InspectionField {
    return { label, value, has_issue: isIssue(value) };
  }

  const TEMPLATE: Record<string, { label: string; fields: Record<string, string> }> = {
    drivability: {
      label: "Drivability, Keys, & History",
      fields: {
        smart_keys: "Smart Keys", other_keys: "Other Keys",
        odor_bio: "Odor/Bio/Environmental/History",
        vehicle_starts: "Vehicle Starts", vehicle_drives: "Vehicle Drives",
      },
    },
    exterior: {
      label: "Exterior",
      fields: {
        front_exterior: "Front Exterior", driver_exterior: "Driver Exterior",
        roof_exterior: "Roof - Exterior", passenger_exterior: "Passenger Exterior",
        rear_exterior: "Rear Exterior", further_disclosures: "Further Disclosures",
      },
    },
    interior: {
      label: "Interior",
      fields: {
        airbags: "Airbags", climate_control: "Climate Control",
        electrical_accessory: "Electrical Accessory", infotainment_radio: "Infotainment/Radio",
        sunroof_operation: "Sunroof Operation", interior_cosmetic: "Interior Cosmetic Damage",
      },
    },
    mechanical: {
      label: "Mechanical & Diagnostic Trouble Codes",
      fields: {
        diagnostic_trouble_codes: "Diagnostic Trouble Codes",
        emissions_catalytic: "Emissions/Catalytic/Exhaust",
        engine_noise: "Engine Noise",
        warning_lights: "Warning Lights & Gauge Cluster",
        active_visible_leaks: "Active Visible Leaks From Engine Or Undercarriage Area",
        engine_oil_sludge: "Engine Oil Sludge",
        vehicle_smoke: "Vehicle Smoke",
        other_mechanical: "Other Mechanical Comments",
      },
    },
    tires: {
      label: "Tires & Wheels",
      fields: {
        driver_front_tire_depth: "Driver Front Tire Depth",
        driver_front_tire_issue: "Driver Front Tire & Wheel Issue",
        driver_rear_tire_depth: "Driver Rear Tire Depth",
        driver_rear_tire_issue: "Driver Rear Tire & Wheel Issue",
        passenger_front_tire_depth: "Passenger Front Tire Depth",
        passenger_front_tire_issue: "Passenger Front Tire & Wheel Issue",
        passenger_rear_tire_depth: "Passenger Rear Tire Depth",
        passenger_rear_tire_issue: "Passenger Rear Tire & Wheel Issue",
      },
    },
  };

  // -- Map NAAA labels (as in body_text) to (sectionId, fieldId) --
  const BODY_TEXT_MAP: Record<string, [string, string]> = {
    "SMART KEYS": ["drivability", "smart_keys"],
    "OTHER KEYS": ["drivability", "other_keys"],
    "ODOR/BIO/ENVIRONMENTAL/HISTORY": ["drivability", "odor_bio"],
    "VEHICLE STARTS": ["drivability", "vehicle_starts"],
    "VEHICLE DRIVES": ["drivability", "vehicle_drives"],
    "FRONT EXTERIOR": ["exterior", "front_exterior"],
    "DRIVER EXTERIOR": ["exterior", "driver_exterior"],
    "ROOF - EXTERIOR": ["exterior", "roof_exterior"],
    "PASSENGER EXTERIOR": ["exterior", "passenger_exterior"],
    "REAR EXTERIOR": ["exterior", "rear_exterior"],
    "FURTHER DISCLOSURES": ["exterior", "further_disclosures"],
    "AIRBAGS": ["interior", "airbags"],
    "CLIMATE CONTROL": ["interior", "climate_control"],
    "ELECTRICAL ACCESSORY": ["interior", "electrical_accessory"],
    "INFOTAINMENT/RADIO": ["interior", "infotainment_radio"],
    "SUNROOF OPERATION": ["interior", "sunroof_operation"],
    "INTERIOR COSMETIC DAMAGE": ["interior", "interior_cosmetic"],
    "DIAGNOSTIC TROUBLE CODES": ["mechanical", "diagnostic_trouble_codes"],
    "EMISSIONS/CATALYTIC/EXHAUST": ["mechanical", "emissions_catalytic"],
    "ENGINE NOISE": ["mechanical", "engine_noise"],
    "WARNING LIGHTS & GAUGE CLUSTER": ["mechanical", "warning_lights"],
    "ACTIVE VISIBLE LEAKS FROM ENGINE OR UNDERCARRIAGE AREA": ["mechanical", "active_visible_leaks"],
    "ENGINE OIL SLUDGE": ["mechanical", "engine_oil_sludge"],
    "VEHICLE SMOKE": ["mechanical", "vehicle_smoke"],
    "OTHER MECHANICAL COMMENTS": ["mechanical", "other_mechanical"],
    "DRIVER FRONT TIRE DEPTH": ["tires", "driver_front_tire_depth"],
    "DRIVER FRONT TIRE & WHEEL ISSUE": ["tires", "driver_front_tire_issue"],
    "DRIVER REAR TIRE DEPTH": ["tires", "driver_rear_tire_depth"],
    "DRIVER REAR TIRE & WHEEL ISSUE": ["tires", "driver_rear_tire_issue"],
    "PASSENGER FRONT TIRE DEPTH": ["tires", "passenger_front_tire_depth"],
    "PASSENGER FRONT TIRE & WHEEL ISSUE": ["tires", "passenger_front_tire_issue"],
    "PASSENGER REAR TIRE DEPTH": ["tires", "passenger_rear_tire_depth"],
    "PASSENGER REAR TIRE & WHEEL ISSUE": ["tires", "passenger_rear_tire_issue"],
  };

  // --- Try parsing body_text first (covers all 32 NAAA fields) ---
  const bodyText = ((report.metadata as Record<string, unknown>)?.report_page as Record<string, unknown>)?.body_text;
  let legacy: Record<string, Record<string, string>> = {};

  if (typeof bodyText === "string" && bodyText.length > 50) {
    const lines = bodyText.split("\n").map((l) => l.trim());
    for (let i = 0; i < lines.length - 1; i++) {
      const label = lines[i].toUpperCase().trim();
      const mapping = BODY_TEXT_MAP[label];
      if (mapping) {
        const value = lines[i + 1].trim();
        if (value && !BODY_TEXT_MAP[value.toUpperCase()]) {
          const [sectionId, fieldId] = mapping;
          legacy[sectionId] = legacy[sectionId] || {};
          legacy[sectionId][fieldId] = value;
          i++; // skip value line
        }
      }
    }
  }

  // --- Fallback: build from structured fields if body_text yielded nothing ---
  if (Object.keys(legacy).length === 0) {
    const vh = report.vehicle_history as { engine_starts?: boolean; drivable?: boolean } | undefined;
    if (vh) {
      const drv: Record<string, string> = {};
      if (vh.engine_starts !== undefined) drv.vehicle_starts = vh.engine_starts ? "Yes - Starts" : "Does Not Start";
      if (vh.drivable !== undefined) drv.vehicle_drives = vh.drivable ? "Yes - Drives" : "Does Not Drive";
      if (Object.keys(drv).length) legacy.drivability = drv;
    }

    const td = report.tire_depths as Record<string, { tread_depth?: string; issue?: string }> | undefined;
    if (td) {
      const tireMap: Record<string, string> = {
        lf: "driver_front", left_front: "driver_front", driver_front: "driver_front",
        rf: "passenger_front", right_front: "passenger_front", passenger_front: "passenger_front",
        lr: "driver_rear", left_rear: "driver_rear", driver_rear: "driver_rear",
        rr: "passenger_rear", right_rear: "passenger_rear", passenger_rear: "passenger_rear",
      };
      const tires: Record<string, string> = {};
      for (const [key, data] of Object.entries(td)) {
        if (!data || typeof data !== "object") continue;
        const dest = tireMap[key.toLowerCase()];
        if (!dest) continue;
        if (data.tread_depth) tires[`${dest}_tire_depth`] = data.tread_depth;
        tires[`${dest}_tire_issue`] = data.issue || "No Issues";
      }
      if (Object.keys(tires).length) legacy.tires = tires;
    }

    if (report.paint_condition) legacy.exterior = { ...legacy.exterior, front_exterior: String(report.paint_condition) };
    if (report.structural_damage) legacy.exterior = { ...legacy.exterior, further_disclosures: `Structural: ${report.structural_damage}` };
    if (report.interior_condition) legacy.interior = { ...legacy.interior, interior_cosmetic: String(report.interior_condition) };
  }

  // Build result — merge legacy values into the NAAA template
  const result: Inspection = {};
  for (const [sectionId, sectionDef] of Object.entries(TEMPLATE)) {
    const incoming = legacy[sectionId] || {};
    const fields: Record<string, InspectionField> = {};
    let issueCount = 0;
    for (const [fieldId, fieldLabel] of Object.entries(sectionDef.fields)) {
      const value = incoming[fieldId] || "Not Inspected";
      const field = makeField(fieldLabel, value);
      if (field.has_issue) issueCount++;
      fields[fieldId] = field;
    }
    result[sectionId] = { label: sectionDef.label, fields, issue_count: issueCount };
  }
  return result;
}

function normalizeAutoCheck(value: unknown): AutoCheckReport | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  const scrapeStatus = normalizeAutoCheckStatus(raw.scrape_status);
  return {
    scrape_status: scrapeStatus,
    attempted_at: typeof raw.attempted_at === "string" ? raw.attempted_at : null,
    autocheck_score: toFiniteInt(raw.autocheck_score),
    score_range_low: firstFiniteInt(raw.score_range_low, raw.scoreRangeLow, raw.score_min, raw.scoreMin, raw.low_score),
    score_range_high: firstFiniteInt(raw.score_range_high, raw.scoreRangeHigh, raw.score_max, raw.scoreMax, raw.high_score),
    score_range_label: normalizeString(raw.score_range_label) || normalizeString(raw.scoreRangeLabel) || normalizeString(raw.comparison_class),
    historical_event_count: firstFiniteInt(raw.historical_event_count, raw.historical_events, raw.event_count, raw.number_of_historical_events, raw.numberOfHistoricalEvents),
    owner_count: firstFiniteInt(raw.owner_count, raw.ownerCount),
    accident_count: firstFiniteInt(raw.accident_count, raw.numberOfAccidents),
    last_reported_event_date: normalizeString(raw.last_reported_event_date) || normalizeString(raw.last_event_date) || normalizeString(raw.lastReportedEventDate),
    last_reported_mileage: firstFiniteInt(raw.last_reported_mileage, raw.last_reported_odometer, raw.last_mileage, raw.lastReportedMileage),
    title_brand_check: normalizeString(raw.title_brand_check),
    odometer_check: normalizeString(raw.odometer_check),
    accident_check: normalizeString(raw.accident_check),
    damage_check: normalizeString(raw.damage_check),
    other_title_brand_event_check: normalizeString(raw.other_title_brand_event_check) || normalizeString(raw.otherTitleBrandEventCheck),
    vehicle_use: normalizeString(raw.vehicle_use),
    buyback_protection: normalizeString(raw.buyback_protection),
    report_logo_url: normalizeString(raw.report_logo_url) || normalizeString(raw.logoUrl),
    full_report_text: normalizeString(raw.full_report_text),
    view_report_href: normalizeString(raw.view_report_href) || normalizeString(raw.reportUrl) || normalizeString(raw.report_url),
    failure_category: normalizeString(raw.failure_category),
    failure_message: normalizeString(raw.failure_message),
  };
}

function normalizeAutoCheckStatus(value: unknown): AutoCheckReport["scrape_status"] {
  if (typeof value !== "string") return "not_attempted";
  const normalized = value.trim().toLowerCase();
  if (normalized === "success" || normalized === "partial" || normalized === "failed" || normalized === "not_attempted") {
    return normalized;
  }
  return "not_attempted";
}

function normalizeString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function toFiniteInt(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.round(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.round(parsed);
  }
  return null;
}

function firstFiniteInt(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = toFiniteInt(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function summarizeAutoCheck(autocheck: AutoCheckReport | null) {
  const fallback = { scoreRangeLow: 0, scoreRangeHigh: 100 };
  if (!autocheck) {
    return fallback;
  }
  const score = autocheck.autocheck_score;
  if (score == null) {
    return fallback;
  }
  const low = clampScore(autocheck.score_range_low ?? score - 3);
  const high = clampScore(Math.max(autocheck.score_range_high ?? score + 2, low + 1));
  return {
    scoreRangeLow: low,
    scoreRangeHigh: high,
  };
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatAutoCheckCheckValue(value: string, tone: "ok" | "issue" | "info" | "muted"): string {
  const normalized = value.trim().toLowerCase();
  if (tone === "ok") {
    return normalized === "ok" ? "OK" : value.trim();
  }
  if (normalized.includes("other use")) return "Other Use Reported";
  const countMatch = normalized.match(/\((\d+)\)|\b(\d+)\b/);
  if (tone === "info") {
    return countMatch?.[1] || countMatch?.[2] ? `Information Reported(${countMatch[1] || countMatch[2]})` : "Information Reported";
  }
  return value;
}

function classifyAutoCheckValue(value: string): "ok" | "issue" | "info" | "muted" {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return "muted";
  if (normalized.includes("not eligible") || normalized.includes("severe") || normalized.includes("salvage") || normalized.includes("junk") || normalized.includes("branded title")) return "issue";
  if (normalized === "ok" || normalized.includes("no accidents reported") || normalized.includes("no damage reported") || normalized.includes("no problem") || normalized.includes("no issues") || normalized.includes("clear") || normalized.includes("eligible") || normalized.includes("qualifies")) return "ok";
  if (normalized.includes("information reported") || normalized.includes("reported") || normalized.includes("other use") || normalized.includes("accident") || normalized.includes("damage") || normalized.includes("brand")) return "info";
  if (normalized.includes("unknown") || normalized.includes("not attempted")) return "muted";
  return "info";
}

function formatTimestamp(value: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatAutoCheckDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", { month: "2-digit", day: "2-digit", year: "numeric" }).format(parsed);
}

type EquipmentSectionItem = { key: string; title: string; meta?: string | null; detail?: string | null; };

function resolveEquipmentSection({
  equipmentFeatures, highValueOptions, installedEquipment,
}: {
  equipmentFeatures: string[]; highValueOptions: EquipmentOption[]; installedEquipment: EquipmentOption[];
}): { title: string; subtitle: string | null; items: EquipmentSectionItem[] } {
  if (equipmentFeatures.length > 0) {
    return {
      title: "EQUIPMENT & FEATURES",
      subtitle: "Vehicle feature list extracted from the condition report.",
      items: equipmentFeatures.map((feature) => ({ key: feature.toLowerCase(), title: feature })),
    };
  }
  const source = highValueOptions.length > 0 ? highValueOptions : installedEquipment;
  const subtitle = highValueOptions.length > 0
    ? "High value OEM options from the listing build data."
    : installedEquipment.length > 0 ? "Installed equipment from the listing build data." : null;
  return {
    title: highValueOptions.length > 0 ? "HIGH VALUE OPTIONS" : "INSTALLED EQUIPMENT",
    subtitle,
    items: source
      .map((item, index) => {
        const title = item.primary_description || item.extended_description;
        if (!title) return null;
        const generics = Array.isArray(item.generics) ? item.generics.map((g) => g?.name).filter(Boolean).join(", ") : "";
        const metaParts = [item.classification, item.installed_reason, item.oem_option_code ? `Code ${item.oem_option_code}` : null, typeof item.msrp === "number" ? `MSRP ${fmtMoney(item.msrp)}` : null].filter(Boolean);
        return { key: `${index}-${title}`.toLowerCase(), title, meta: metaParts.join(" \u00b7 ") || null, detail: item.extended_description || generics || null };
      })
      .filter(Boolean) as EquipmentSectionItem[],
  };
}

function sanitizePublicText(text: string): string {
  let cleaned = text;
  cleaned = cleaned.replace(/(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g, "");
  cleaned = cleaned.replace(/[\w.+-]+@[\w.-]+\.\w{2,}/g, "");
  cleaned = cleaned.replace(/https?:\/\/[^\s,)]+/gi, "");
  cleaned = cleaned.replace(/www\.[^\s,)]+/gi, "");
  cleaned = cleaned.replace(/\b(Manheim|ADESA|TradeRev|SmartAuction|Smart Auction|Ally\s+Smart\s*Auction|OPENLANE|OVE\.com|ACV\s+Auctions|ACV|BacklotCars|Backlot\s+Cars)\b/gi, "");
  return cleaned.replace(/\s{2,}/g, " ").trim();
}

function fmtMoney(value: number | null | undefined): string {
  if (!value) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value);
}

function fmtMiles(value: number | null | undefined): string {
  if (!value) return "N/A";
  return new Intl.NumberFormat("en-US").format(value) + " mi";
}
