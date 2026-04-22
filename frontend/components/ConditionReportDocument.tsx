/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

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
  section?: string;
  section_label?: string;
  panel?: string;
  condition?: string;
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
  owner_count?: number | null;
  accident_count?: number | null;
  title_brand_check?: string | null;
  odometer_check?: string | null;
  accident_check?: string | null;
  damage_check?: string | null;
  vehicle_use?: string | null;
  buyback_protection?: string | null;
  full_report_text?: string | null;
  view_report_href?: string | null;
  failure_category?: string | null;
  failure_message?: string | null;
};

type InspectionField = {
  label: string;
  value: string;
  has_issue: boolean;
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

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";
const AUCTION_DEFAULT = "/assets/images/portfolio/VCH Auction default image.webp";

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

export function ConditionReportDocument({ vin }: { vin: string }) {
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canRevealVin, setCanRevealVin] = useState(false);
  const [authorized, setAuthorized] = useState<boolean | null>(null);

  // Gallery state
  const [galleryIndex, setGalleryIndex] = useState(0);
  const [activeCategory, setActiveCategory] = useState("all");
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      setLoading(true);
      setError(null);

      // Load auth state first so we can pass the token to the API
      const auth = await loadValidAuthState();
      if (cancelled) return;

      const adminUser = isAdminUser(auth);
      setAuthorized(adminUser);

      if (!adminUser) {
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

      // Check VIN reveal permissions
      if (auth?.accessToken) {
        const [statusRes, garageRes] = await Promise.all([
          apiFetch<{ is_preapproved: boolean }>("/me/account-status", {}, auth.accessToken),
          apiFetch<Array<{ vin: string }>>("/me/garage", {}, auth.accessToken),
        ]);
        if (cancelled) return;
        const preapproved = statusRes.status === "ok" && Boolean(statusRes.data?.is_preapproved);
        const inGarage =
          garageRes.status === "ok" &&
          Array.isArray(garageRes.data) &&
          garageRes.data.some((item) => item.vin === vin);
        setCanRevealVin(preapproved && inGarage);
      }

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
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [navigateGallery, lightboxOpen]);

  // Announcements
  const announcements = useMemo(() => parseAnnouncements(report, crMetadata), [report, crMetadata]);
  const remarks = Array.isArray(report.remarks) ? report.remarks.map(String) : [];

  // Inspection — prefer structured, fall back to legacy
  const inspection = useMemo((): Inspection | null => {
    const raw = report.inspection as Inspection | undefined;
    if (raw && typeof raw === "object" && Object.keys(raw).length > 0) return raw;
    return buildLegacyInspection(report);
  }, [report]);

  // Title info
  const titleStatus = typeof report.title_status === "string" ? report.title_status : null;
  const titleState = typeof report.title_state === "string" ? report.title_state : null;
  const titleBranding = typeof report.title_branding === "string" ? report.title_branding : null;

  // AutoCheck
  const autocheck = useMemo(() => normalizeAutoCheck(report.autocheck), [report]);
  const autoCheckSummary = useMemo(() => summarizeAutoCheck(autocheck), [autocheck]);

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

  if (loading || authorized === null) {
    return (
      <main className="page-stack">
        <section className="card">Loading condition report...</section>
      </main>
    );
  }

  if (!authorized) {
    return (
      <main className="page-stack">
        <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vin)}` as any}>
          Back to Vehicle
        </Link>
        <section className="card">Condition reports are only available to administrative users.</section>
      </main>
    );
  }

  if (error || !vehicle) {
    return (
      <main className="page-stack">
        <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vin)}` as any}>
          Back to Vehicle
        </Link>
        <section className="card">{error || "Condition report unavailable."}</section>
      </main>
    );
  }

  return (
    <>
      <main className="page-stack cr-doc">
        {/* ── HEADER ── */}
        <section className="cr-doc-header">
          <div className="cr-doc-header-inner">
            <h2 className="cr-doc-brand">VCH Condition Report</h2>
            <div className="cr-doc-header-actions">
              <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vehicle.public_slug || vehicle.vin)}` as any}>
                Back to Vehicle
              </Link>
              {crUrl && (
                <button className="button" onClick={() => window.open(crUrl, "_blank", "noopener,noreferrer")}>
                  See Original CR
                </button>
              )}
              <button className="button ghost" onClick={() => window.print()}>Print</button>
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
                  <button className="cr-gallery-arrow cr-gallery-arrow-left" onClick={() => navigateGallery(-1)} aria-label="Previous image">&lsaquo;</button>
                  <button className="cr-gallery-arrow cr-gallery-arrow-right" onClick={() => navigateGallery(1)} aria-label="Next image">&rsaquo;</button>
                </>
              )}
              <div className="cr-gallery-counter">
                {filteredImages.length > 0 ? `${galleryIndex + 1} of ${filteredImages.length}` : "No photos"}
                <button className="cr-gallery-fullscreen" onClick={() => setLightboxOpen(true)} aria-label="Full screen">&#x26F6;</button>
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
            {inspection && (
              <div className="cr-panel-section">
                <h4 className="cr-panel-heading">Issues</h4>
                <div className="cr-issues-table">
                  {INSPECTION_SECTION_ORDER.map((sectionId) => {
                    const section = inspection[sectionId];
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
        <div className="cr-inspection-banner">INSPECTION</div>

        {/* ── NAAA INSPECTION SECTIONS ── */}
        {inspection && INSPECTION_SECTION_ORDER.map((sectionId) => {
          const section = inspection[sectionId];
          if (!section) return null;
          const fields = Object.values(section.fields);
          return (
            <section key={sectionId} className="cr-section">
              <h3 className="cr-section-bar">{section.label}</h3>
              <div className="cr-inspection-grid">
                {fields.map((field) => {
                  const isUnavailable = field.value.toLowerCase() === "not available";
                  const cls = field.has_issue ? " cr-field-issue" : isUnavailable ? " cr-field-unavailable" : "";
                  return (
                    <div key={field.label} className={`cr-field-cell${cls}`}>
                      <span className="cr-field-label">{field.label}</span>
                      <span className="cr-field-value">{field.value}</span>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}

        {/* ── TITLE & VEHICLE HISTORY (AutoCheck integrated) ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">TITLE &amp; VEHICLE HISTORY</h3>
          <div className="cr-title-history-content">
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
                  <article className="cr-autocheck-summary-card">
                    <div className="cr-autocheck-summary-head">
                      <span className="cr-autocheck-mini-label">Experian AutoCheck</span>
                      <span className={`cr-autocheck-status cr-autocheck-status-${autoCheckSummary.statusTone}`}>
                        {autoCheckSummary.statusLabel}
                      </span>
                    </div>
                    <h4 className="cr-autocheck-title">History snapshot for {vehicle.year} {vehicle.make} {vehicle.model}</h4>
                    <div className="cr-autocheck-summary-grid">
                      {renderAutoCheckSummaryValue("Owners", autocheck.owner_count)}
                      {renderAutoCheckSummaryValue("Accidents", autocheck.accident_count)}
                      {renderAutoCheckSummaryValue("Title Brand", autocheck.title_brand_check || "N/A")}
                      {renderAutoCheckSummaryValue("Odometer", autocheck.odometer_check || "N/A")}
                    </div>
                    {autocheck.attempted_at && (
                      <p className="cr-autocheck-meta">Captured {formatTimestamp(autocheck.attempted_at)}</p>
                    )}
                  </article>

                  <article className="cr-autocheck-score-card">
                    <div className="cr-autocheck-score-topline">
                      <span className="cr-autocheck-mini-label">AutoCheck Score</span>
                      {autocheck.autocheck_score != null && (
                        <span className={`cr-autocheck-score-band cr-autocheck-score-band-${autoCheckSummary.scoreTone}`}>
                          {autoCheckSummary.scoreBand}
                        </span>
                      )}
                    </div>
                    {autocheck.autocheck_score != null ? (
                      <>
                        <div className="cr-autocheck-gauge">
                          <div
                            className="cr-autocheck-gauge-arc"
                            style={{
                              background: `conic-gradient(from 180deg, ${autoCheckSummary.scoreColor} 0deg ${Math.max(0, Math.min(180, (autocheck.autocheck_score / 100) * 180))}deg, rgba(255,255,255,0.08) ${Math.max(0, Math.min(180, (autocheck.autocheck_score / 100) * 180))}deg 180deg, transparent 180deg 360deg)`,
                            }}
                          />
                          <div className="cr-autocheck-gauge-cutout" />
                          <div className="cr-autocheck-gauge-center">
                            <strong>{autocheck.autocheck_score}</strong>
                            <span>/ 100</span>
                          </div>
                        </div>
                        <div className="cr-autocheck-scale">
                          <span>0</span><span>50</span><span>100</span>
                        </div>
                        <p className="cr-autocheck-score-copy">{autoCheckSummary.scoreDescription}</p>
                      </>
                    ) : (
                      <p className="cr-comments">AutoCheck score not provided for this vehicle.</p>
                    )}
                  </article>
                </div>

                <div className="cr-autocheck-check-grid">
                  {renderAutoCheckCheck("Major State Title Brand Check", autocheck.title_brand_check)}
                  {renderAutoCheckCheck("Odometer Check", autocheck.odometer_check)}
                  {renderAutoCheckCheck("Accident Check", autocheck.accident_check)}
                  {renderAutoCheckCheck("Damage Check", autocheck.damage_check)}
                  {renderAutoCheckCheck("Vehicle Usage Check", autocheck.vehicle_use)}
                  {renderAutoCheckCheck("Buyback Protection", autocheck.buyback_protection)}
                </div>

                {(autocheck.full_report_text || autocheck.view_report_href) && (
                  <details className="cr-autocheck-details">
                    <summary>
                      <span>Full AutoCheck Report</span>
                      <span className="cr-autocheck-details-hint">Expand</span>
                    </summary>
                    <div className="cr-autocheck-details-body">
                      {autocheck.view_report_href && (
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
                      "We could not retrieve the Experian AutoCheck history on this pass. The rest of the condition report is still available."}
                  </p>
                </div>
                {autocheck.attempted_at && (
                  <span className="cr-autocheck-attempted">Attempted {formatTimestamp(autocheck.attempted_at)}</span>
                )}
              </div>
            )}
          </div>
        </section>

        {/* ── PROBLEM HIGHLIGHTS ── */}
        {problemHighlights.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">PROBLEM HIGHLIGHTS</h3>
            <ul className="cr-announce-list cr-problem-list">
              {problemHighlights.map((h, i) => <li key={i}>{h}</li>)}
            </ul>
          </section>
        )}

        {/* ── EQUIPMENT / FEATURES ── */}
        {equipmentSection.items.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">{equipmentSection.title}</h3>
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
          </section>
        )}

        {/* ── DAMAGE REPORT ── */}
        {damageItems.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">
              DAMAGE REPORT
              {damageSummary && <span className="cr-damage-count"> &mdash; {damageSummary.total_items ?? damageItems.length} item{(damageSummary.total_items ?? damageItems.length) !== 1 ? "s" : ""}</span>}
              {damageSummary?.structural_issue && <span className="cr-structural-flag"> STRUCTURAL ISSUE</span>}
            </h3>
            <table className="cr-damage-table">
              <thead>
                <tr><th>Section</th><th>Panel</th><th>Condition</th><th>Severity</th></tr>
              </thead>
              <tbody>
                {damageItems.map((d, i) => (
                  <tr key={i}>
                    <td>{d.section_label || d.section || "\u2014"}</td>
                    <td>{d.panel || "\u2014"}</td>
                    <td>{d.condition || "\u2014"}</td>
                    <td>
                      <span className={`cr-severity cr-severity-${d.severity_color || "gray"}`}>
                        {d.reported_severity || d.severity_label || "\u2014"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {severitySummary && <p className="cr-comments" style={{ fontSize: 13, color: "var(--muted)" }}>{severitySummary}</p>}
          </section>
        )}

        {/* ── SELLER COMMENTS ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">SELLER COMMENTS</h3>
          {sellerCommentsItems.length > 0 ? (
            <ul className="cr-announce-list">
              {sellerCommentsItems.map((c, i) => <li key={i}>{sanitizePublicText(c)}</li>)}
            </ul>
          ) : (
            <p className="cr-comments">{sanitizePublicText(vehicle.seller_comments || "") || "No comments provided."}</p>
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

        {/* ── ORIGINAL CR BUTTON ── */}
        {crUrl && (
          <section className="cr-section" style={{ textAlign: "center", padding: "20px 0" }}>
            <button className="button" onClick={() => window.open(crUrl, "_blank", "noopener,noreferrer")} style={{ fontSize: 16, padding: "12px 32px" }}>
              See Original Condition Report
            </button>
          </section>
        )}
      </main>

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

        /* ── Inspection Grid (3-col) ── */
        .cr-inspection-grid {
          display: grid; grid-template-columns: repeat(3, 1fr);
          gap: 0; padding: 0;
        }
        .cr-field-cell {
          padding: 10px 14px;
          border-bottom: 1px solid #333;
          border-right: 1px solid #333;
        }
        .cr-field-cell:nth-child(3n) { border-right: none; }
        .cr-field-label {
          display: block; font-size: 11px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.3px;
          color: #aaa; margin-bottom: 2px;
        }
        .cr-field-value { display: block; font-size: 14px; color: #e0e0e0; font-weight: 500; }
        .cr-field-issue .cr-field-label { color: #e74c3c; }
        .cr-field-issue .cr-field-value { color: #e74c3c; font-weight: 700; }
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
        .cr-severity-red { background: #4d1a1a; color: #e74c3c; }
        .cr-severity-gray { background: #333; color: #aaa; }

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
        .cr-autocheck-hero { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr); gap: 14px; }
        .cr-autocheck-summary-card,
        .cr-autocheck-score-card,
        .cr-autocheck-check-card,
        .cr-autocheck-unavailable,
        .cr-autocheck-details {
          border: 1px solid #3d3d52; border-radius: 10px;
          background: rgba(255,255,255,0.025);
        }
        .cr-autocheck-summary-card,
        .cr-autocheck-score-card { padding: 16px; }
        .cr-autocheck-summary-head,
        .cr-autocheck-score-topline {
          display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
        }
        .cr-autocheck-mini-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: #9da8c3; font-weight: 700; }
        .cr-autocheck-status,
        .cr-autocheck-score-band {
          display: inline-flex; align-items: center; justify-content: center;
          padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.5px;
        }
        .cr-autocheck-status-good,
        .cr-autocheck-score-band-strong { background: rgba(69,138,92,0.2); color: #8fe0a6; border: 1px solid rgba(69,138,92,0.45); }
        .cr-autocheck-status-warning,
        .cr-autocheck-score-band-watch { background: rgba(201,164,74,0.16); color: #f1cb76; border: 1px solid rgba(201,164,74,0.38); }
        .cr-autocheck-status-muted,
        .cr-autocheck-score-band-muted { background: rgba(113,126,152,0.14); color: #c6cfdf; border: 1px solid rgba(113,126,152,0.32); }
        .cr-autocheck-title { margin: 12px 0 14px; font-size: 20px; line-height: 1.15; }
        .cr-autocheck-summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .cr-autocheck-summary-stat {
          border: 1px solid #33384c; border-radius: 8px; padding: 12px;
          background: rgba(15,20,32,0.55); display: grid; gap: 6px;
        }
        .cr-autocheck-summary-stat span { font-size: 11px; color: #a9b2c1; text-transform: uppercase; letter-spacing: 0.5px; }
        .cr-autocheck-summary-stat strong { font-size: 20px; color: #f4f6fa; }
        .cr-autocheck-meta { margin: 12px 0 0; color: #9fa8bb; font-size: 12px; }
        .cr-autocheck-gauge {
          position: relative; width: 100%; max-width: 260px;
          aspect-ratio: 1.8 / 1.1; margin: 14px auto 6px;
        }
        .cr-autocheck-gauge-arc {
          position: absolute; inset: 0;
          border-radius: 260px 260px 0 0; clip-path: inset(0 0 50% 0);
        }
        .cr-autocheck-gauge-cutout {
          position: absolute; inset: 20px 20px 0 20px;
          border-radius: 220px 220px 0 0; background: #151b29;
          clip-path: inset(0 0 50% 0);
        }
        .cr-autocheck-gauge-center {
          position: absolute; left: 50%; bottom: 0; transform: translateX(-50%);
          display: grid; justify-items: center; gap: 2px;
        }
        .cr-autocheck-gauge-center strong { font-size: 48px; line-height: 1; color: #f3f6fd; }
        .cr-autocheck-gauge-center span { font-size: 12px; color: #a7b2c7; letter-spacing: 0.5px; text-transform: uppercase; }
        .cr-autocheck-scale { display: flex; justify-content: space-between; gap: 12px; color: #96a1b7; font-size: 12px; }
        .cr-autocheck-score-copy { margin: 12px 0 0; color: #d9e1f2; line-height: 1.6; }
        .cr-autocheck-check-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .cr-autocheck-check-card { padding: 14px; display: grid; gap: 10px; }
        .cr-autocheck-check-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .cr-autocheck-check-label { font-size: 13px; color: #dce3f1; font-weight: 700; }
        .cr-autocheck-check-value { color: #c1cbde; font-size: 13px; line-height: 1.5; }
        .cr-autocheck-chip {
          display: inline-flex; align-items: center; justify-content: center;
          min-width: 94px; padding: 4px 10px; border-radius: 999px;
          font-size: 11px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.5px; white-space: nowrap;
        }
        .cr-autocheck-chip-ok { background: rgba(69,138,92,0.2); color: #92e2a9; border: 1px solid rgba(69,138,92,0.45); }
        .cr-autocheck-chip-issue { background: rgba(194,100,88,0.18); color: #f4a095; border: 1px solid rgba(194,100,88,0.38); }
        .cr-autocheck-chip-info { background: rgba(90,119,177,0.18); color: #9cc5ff; border: 1px solid rgba(90,119,177,0.38); }
        .cr-autocheck-chip-muted { background: rgba(113,126,152,0.14); color: #c6cfdf; border: 1px solid rgba(113,126,152,0.32); }
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
          .cr-summary-panel { max-height: none; }
          .cr-inspection-grid { grid-template-columns: 1fr; }
          .cr-image-grid { grid-template-columns: repeat(2, 1fr); }
          .cr-equipment-grid { grid-template-columns: 1fr; }
          .cr-autocheck-hero, .cr-autocheck-check-grid, .cr-autocheck-summary-grid { grid-template-columns: 1fr; }
          .cr-autocheck-unavailable { flex-direction: column; }
          .cr-field-cell { border-right: none; }
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
        :global(:root[data-theme="light"]) .cr-field-cell { border-bottom-color: var(--line); border-right-color: var(--line); }
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
        :global(:root[data-theme="light"]) .cr-severity-red { background: #fde8e8; color: #b91c1c; }
        :global(:root[data-theme="light"]) .cr-severity-gray { background: #edf0f5; color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-equipment-card { border-color: var(--line); background: var(--surface-soft); }
        :global(:root[data-theme="light"]) .cr-equipment-title { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-equipment-detail { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-grid-thumb { border-color: #ccc; }
        :global(:root[data-theme="light"]) .cr-autocheck-summary-card,
        :global(:root[data-theme="light"]) .cr-autocheck-score-card,
        :global(:root[data-theme="light"]) .cr-autocheck-check-card,
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable,
        :global(:root[data-theme="light"]) .cr-autocheck-details { border-color: var(--line); background: var(--surface-soft); }
        :global(:root[data-theme="light"]) .cr-autocheck-mini-label { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-title { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-summary-stat { border-color: var(--line); background: var(--surface-strong); }
        :global(:root[data-theme="light"]) .cr-autocheck-summary-stat span { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-summary-stat strong { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-meta { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-cutout { background: #fff; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-center strong { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-gauge-center span { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-scale { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-score-copy { color: #334155; }
        :global(:root[data-theme="light"]) .cr-autocheck-check-label { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-check-value { color: #334155; }
        :global(:root[data-theme="light"]) .cr-autocheck-attempted { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-details summary { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-details-hint { color: var(--muted); }
        :global(:root[data-theme="light"]) .cr-autocheck-details-body { border-top-color: var(--line); }
        :global(:root[data-theme="light"]) .cr-autocheck-report-text { background: #f5f7fa; border-color: var(--line); color: #334155; }
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable strong { color: #1a2a40; }
        :global(:root[data-theme="light"]) .cr-autocheck-unavailable p { color: #334155; }
      `}</style>
    </>
  );
}

/* ── Helpers ── */

function renderAutoCheckSummaryValue(label: string, value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="cr-autocheck-summary-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function renderAutoCheckCheck(label: string, value: string | null | undefined) {
  if (!value) return null;
  const tone = classifyAutoCheckValue(value);
  return (
    <article className="cr-autocheck-check-card">
      <div className="cr-autocheck-check-head">
        <span className="cr-autocheck-check-label">{label}</span>
        <span className={`cr-autocheck-chip cr-autocheck-chip-${tone}`}>{autoCheckToneLabel(tone)}</span>
      </div>
      <div className="cr-autocheck-check-value">{value}</div>
    </article>
  );
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
    owner_count: toFiniteInt(raw.owner_count),
    accident_count: toFiniteInt(raw.accident_count),
    title_brand_check: normalizeString(raw.title_brand_check),
    odometer_check: normalizeString(raw.odometer_check),
    accident_check: normalizeString(raw.accident_check),
    damage_check: normalizeString(raw.damage_check),
    vehicle_use: normalizeString(raw.vehicle_use),
    buyback_protection: normalizeString(raw.buyback_protection),
    full_report_text: normalizeString(raw.full_report_text),
    view_report_href: normalizeString(raw.view_report_href),
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

function summarizeAutoCheck(autocheck: AutoCheckReport | null) {
  if (!autocheck) {
    return { statusLabel: "Unavailable", statusTone: "muted", scoreBand: "Unavailable", scoreTone: "muted", scoreColor: "#7f8aa3", scoreDescription: "AutoCheck score data is not available for this vehicle." } as const;
  }
  const statusTone = autocheck.scrape_status === "success" ? "good" : autocheck.scrape_status === "partial" ? "warning" : "muted";
  const score = autocheck.autocheck_score;
  if (score == null) {
    return { statusLabel: autocheck.scrape_status.replaceAll("_", " "), statusTone, scoreBand: "Unavailable", scoreTone: "muted", scoreColor: "#7f8aa3", scoreDescription: "AutoCheck score was not included in this report payload." } as const;
  }
  if (score >= 85) {
    return { statusLabel: autocheck.scrape_status.replaceAll("_", " "), statusTone, scoreBand: "Strong", scoreTone: "strong", scoreColor: "#6d85ff", scoreDescription: "This score sits in the stronger end of AutoCheck's 0-100 scale." } as const;
  }
  if (score >= 70) {
    return { statusLabel: autocheck.scrape_status.replaceAll("_", " "), statusTone, scoreBand: "Watch", scoreTone: "watch", scoreColor: "#d5a54b", scoreDescription: "This score is worth a closer look alongside the check results below." } as const;
  }
  return { statusLabel: autocheck.scrape_status.replaceAll("_", " "), statusTone, scoreBand: "Watch", scoreTone: "watch", scoreColor: "#d96b63", scoreDescription: "This score falls on the lower end of AutoCheck's 0-100 scale and should be reviewed carefully." } as const;
}

function classifyAutoCheckValue(value: string): "ok" | "issue" | "info" | "muted" {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return "muted";
  if (normalized === "ok" || normalized.includes("no accidents reported") || normalized.includes("no damage reported") || normalized.includes("no problem") || normalized.includes("no issues") || normalized.includes("clear") || normalized.includes("eligible")) return "ok";
  if (normalized.includes("problem reported") || normalized.includes("information reported") || normalized.includes("reported") || normalized.includes("other use") || normalized.includes("accident") || normalized.includes("damage") || normalized.includes("brand") || normalized.includes("not eligible")) return "issue";
  if (normalized.includes("unknown") || normalized.includes("not attempted")) return "muted";
  return "info";
}

function autoCheckToneLabel(tone: "ok" | "issue" | "info" | "muted"): string {
  switch (tone) {
    case "ok": return "OK";
    case "issue": return "Reported";
    case "info": return "Info";
    default: return "Unknown";
  }
}

function formatTimestamp(value: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
  } catch {
    return value;
  }
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
