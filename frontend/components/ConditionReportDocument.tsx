/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";

type VehicleDetail = {
  vin: string;
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
    images?: Array<{ url: string; role?: string; display_order?: number; is_primary?: boolean } | string>;
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

type TireDepth = {
  position_label?: string;
  tread_depth?: string;
  brand?: string;
  size?: string;
  wheel_type?: string;
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";
const AUCTION_DEFAULT = "/assets/images/portfolio/VCH Auction default image.webp";

export function ConditionReportDocument({ vin }: { vin: string }) {
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightboxImage, setLightboxImage] = useState<string | null>(null);

  useEffect(() => {
    async function loadVehicle() {
      setLoading(true);
      setError(null);
      const response = await apiFetch<VehicleDetail>(`/inventory/${encodeURIComponent(vin)}`);
      if (response.status !== "ok") {
        setVehicle(null);
        setError(response.error?.message || "Unable to load condition report.");
        setLoading(false);
        return;
      }
      setVehicle(response.data);
      setLoading(false);
    }
    void loadVehicle();
  }, [vin]);

  // Extract structured data from wherever it lives
  const report = useMemo(() => {
    if (!vehicle) return {};
    return vehicle.condition_report || vehicle.display_context?.condition_report || {};
  }, [vehicle]);

  const crUrl = vehicle?.condition_report_url || null;
  const crMetadata = (report.metadata || {}) as Record<string, unknown>;
  const crReportLink = (crMetadata.report_link || {}) as Record<string, unknown>;
  const crGrade = vehicle?.condition_report_grade || vehicle?.condition_grade || (crReportLink.title as string) || null;
  const galleryImages = resolveReportImages(vehicle);
  const inspectionImages = vehicle?.display_context?.inspection_images || [];
  const disclosureImages = vehicle?.display_context?.disclosure_images || [];
  const allImages = [...galleryImages, ...inspectionImages, ...disclosureImages];
  const primaryImage = resolveHeroImage(vehicle) || allImages[0] || AUCTION_DEFAULT;

  // Parse announcements
  const announcements = useMemo(() => {
    const raw = report.announcements;
    if (Array.isArray(raw) && raw.length > 0) return raw.map(String);
    // Try to extract from raw_text
    const rawText = typeof report.raw_text === "string" ? report.raw_text : "";
    const annoMatch = rawText.match(/Announcements\s*(.*?)(?:Remarks|Seller Comments|$)/si);
    if (annoMatch && annoMatch[1]) {
      const text = annoMatch[1].replace(/No Announcements Present/gi, "").trim();
      if (text && text !== "No") return [text];
    }
    return [];
  }, [report]);

  // ── Structured fields from richer report shape ──
  const vehicleHistory = report.vehicle_history as { engine_starts?: boolean; drivable?: boolean; owners?: number; accidents?: number } | undefined;
  const damageItems = Array.isArray(report.damage_items) ? (report.damage_items as DamageItem[]) : [];
  const damageSummary = report.damage_summary as { total_items?: number; by_color?: Record<string, number>; by_section?: Record<string, number>; structural_issue?: boolean } | undefined;
  const tireDepths = report.tire_depths as Record<string, TireDepth> | undefined;
  const problemHighlights = Array.isArray(report.problem_highlights) ? report.problem_highlights.map(String) : [];
  const remarks = Array.isArray(report.remarks) ? report.remarks.map(String) : [];
  const sellerCommentsItems = Array.isArray(report.seller_comments_items) ? report.seller_comments_items.map(String) : [];
  const severitySummary = typeof report.severity_summary === "string" ? report.severity_summary : null;
  const aiSummary = typeof report.ai_summary === "string" ? report.ai_summary : null;
  const titleStatus = typeof report.title_status === "string" ? report.title_status : null;
  const titleState = typeof report.title_state === "string" ? report.title_state : null;
  const titleBranding = typeof report.title_branding === "string" ? report.title_branding : null;
  const overallGrade = typeof report.overall_grade === "string" ? report.overall_grade : null;

  // Parse key info — prefer structured vehicle_history, fall back to raw text parsing
  const vehicleInfo = useMemo(() => {
    if (!vehicle) return {};
    const norm = vehicle.features_normalized || {};
    const rawText = typeof report.raw_text === "string" ? report.raw_text : "";

    // Prefer structured vehicle_history; fall back to regex for older flat reports
    let owners: string | null = vehicleHistory?.owners != null ? String(vehicleHistory.owners) : null;
    let accidents: string | null = vehicleHistory?.accidents != null ? String(vehicleHistory.accidents) : null;
    if (!owners) {
      const ownersMatch = rawText.match(/Owners(\d+)/);
      if (ownersMatch) owners = ownersMatch[1];
    }
    if (!accidents) {
      const accidentsMatch = rawText.match(/AccidentsACDNT(\d+)/i) || rawText.match(/Accidents(\d+)/i);
      if (accidentsMatch) accidents = accidentsMatch[1];
    }

    // Title info — prefer structured fields
    const resolvedTitle = titleStatus || (() => {
      const titleMatch = rawText.match(/Title Status(.*?)Title State/i);
      return titleMatch ? titleMatch[1].trim() : null;
    })();

    // Seller
    let seller: string | null = null;
    const sellerMatch = rawText.match(/Contact:\s*(.*?)(?:\d+\.\d+|Contact|$)/i);
    if (sellerMatch) seller = sellerMatch[1].replace(/View seller.*$/i, "").trim();

    return {
      exterior_color: String(norm.exterior_color || report.exterior_color || ""),
      interior_color: String(norm.interior_color || report.interior_color || ""),
      engine: String(norm.engine_type || vehicle.engine_type || ""),
      drivetrain: String(vehicle.drivetrain || norm.drivetrain || ""),
      owners,
      accidents,
      titleStatus: resolvedTitle,
      seller,
    };
  }, [vehicle, report, vehicleHistory, titleStatus]);

  if (loading) {
    return (
      <main className="page-stack">
        <section className="card">Loading condition report...</section>
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
            <div>
              <h2 className="cr-doc-brand">VCH Condition Report</h2>
            </div>
            <div className="cr-doc-header-actions">
              <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vehicle.vin)}` as any}>
                Back to Vehicle
              </Link>
              {crUrl && (
                <button className="button" onClick={() => window.open(crUrl, '_blank', 'noopener,noreferrer')}>
                  See Original CR
                </button>
              )}
              <button className="button ghost" onClick={() => window.print()}>
                Print
              </button>
            </div>
          </div>
        </section>

        {/* ── VEHICLE DETAILS (matches sample layout) ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">
            VEHICLE DETAILS &mdash; {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim || ""}
          </h3>
          <table className="cr-details-table">
            <tbody>
              <tr>
                <td className="cr-td-label">VIN:</td>
                <td>{vehicle.vin}</td>
                <td className="cr-td-label">Body Style:</td>
                <td>{vehicle.body_type || "N/A"}</td>
                <td className="cr-td-label">Odometer:</td>
                <td>{fmtMiles(vehicle.odometer)}</td>
              </tr>
              <tr>
                <td className="cr-td-label">Ext Color:</td>
                <td>{vehicleInfo.exterior_color || "N/A"}</td>
                <td className="cr-td-label">Int Color:</td>
                <td>{vehicleInfo.interior_color || "N/A"}</td>
                <td className="cr-td-label">Drivetrain:</td>
                <td>{vehicleInfo.drivetrain || "N/A"}</td>
              </tr>
              <tr>
                <td className="cr-td-label">Seller:</td>
                <td>{vehicleInfo.seller || vehicle.auction_house || "N/A"}</td>
                <td className="cr-td-label">Location:</td>
                <td>{vehicle.pickup_location || `${vehicle.location_state || ""} ${vehicle.location_zip || ""}`.trim() || "N/A"}</td>
                <td className="cr-td-label">Engine:</td>
                <td>{vehicleInfo.engine || "N/A"}</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* ── VEHICLE IMAGES ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">VEHICLE IMAGES</h3>
          <div className="cr-images-layout">
            <div className="cr-thumb-col">
              {allImages.slice(0, 8).map((img, i) => (
                <div key={i} className="cr-thumb" onClick={() => setLightboxImage(img)}>
                  <img src={img} alt={`View ${i + 1}`} onError={e => { e.currentTarget.src = FALLBACK_IMAGE; }} />
                </div>
              ))}
            </div>
            <div className="cr-hero-col" onClick={() => setLightboxImage(primaryImage)}>
              <img src={primaryImage} alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`} onError={e => { e.currentTarget.src = FALLBACK_IMAGE; }} />
            </div>
            {crGrade && (
              <div className="cr-grade-col">
                <div className="cr-grade-card">
                  <span className="cr-grade-label">Grade</span>
                  <span className="cr-grade-value">{crGrade}</span>
                  {overallGrade && overallGrade !== crGrade && <span className="cr-grade-desc">{overallGrade}</span>}
                </div>
                <ul className="cr-grade-checks">
                  {(report.structural_damage !== undefined || damageSummary?.structural_issue !== undefined) && (
                    <li>Structural Damage: {damageSummary?.structural_issue ? "Yes" : String(report.structural_damage || "None reported")}</li>
                  )}
                  <li>Engine Starts: {vehicleHistory?.engine_starts === false ? "No" : "Yes"}</li>
                  <li>Drivable: {vehicleHistory?.drivable === false ? "No" : "Yes"}</li>
                </ul>
              </div>
            )}
          </div>
        </section>

        {/* ── GRADING / PRICING ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">GRADING &amp; PRICING</h3>
          <div className="cr-kpi-row">
            <div className="cr-kpi">
              <span className="cr-kpi-label">Condition Grade</span>
              <span className="cr-kpi-value">{crGrade || "Pending"}</span>
            </div>
            <div className="cr-kpi">
              <span className="cr-kpi-label">MMR Value</span>
              <span className="cr-kpi-value">{fmtMoney(vehicle.mmr)}</span>
            </div>
            <div className="cr-kpi">
              <span className="cr-kpi-label">Asking Price</span>
              <span className="cr-kpi-value">{fmtMoney(vehicle.price_asking)}</span>
            </div>
            {vehicleInfo.owners && (
              <div className="cr-kpi">
                <span className="cr-kpi-label">Owners</span>
                <span className="cr-kpi-value">{vehicleInfo.owners}</span>
              </div>
            )}
            {vehicleInfo.accidents && (
              <div className="cr-kpi">
                <span className="cr-kpi-label">Accidents</span>
                <span className="cr-kpi-value">{vehicleInfo.accidents}</span>
              </div>
            )}
          </div>
        </section>

        {/* ── PROBLEM HIGHLIGHTS (top summary from richer report) ── */}
        {problemHighlights.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">PROBLEM HIGHLIGHTS</h3>
            <ul className="cr-announce-list cr-problem-list">
              {problemHighlights.map((h, i) => <li key={i}>{h}</li>)}
            </ul>
          </section>
        )}

        {/* ── AI SUMMARY ── */}
        {aiSummary && (
          <section className="cr-section">
            <h3 className="cr-section-bar">AI CONDITION SUMMARY</h3>
            <p className="cr-comments">{aiSummary}</p>
          </section>
        )}

        {/* ── ANNOUNCEMENTS ── */}
        {announcements.length > 0 ? (
          <section className="cr-section">
            <h3 className="cr-section-bar">ANNOUNCEMENTS</h3>
            <ul className="cr-announce-list">
              {announcements.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </section>
        ) : (
          <section className="cr-section">
            <h3 className="cr-section-bar">ANNOUNCEMENTS</h3>
            <p className="cr-empty">No announcements present. Green Light.</p>
          </section>
        )}

        {/* ── REMARKS ── */}
        {remarks.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">REMARKS</h3>
            <ul className="cr-announce-list">
              {remarks.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </section>
        )}

        {/* ── SELLER COMMENTS ── */}
        <section className="cr-section">
          <h3 className="cr-section-bar">SELLER COMMENTS</h3>
          {sellerCommentsItems.length > 0 ? (
            <ul className="cr-announce-list">
              {sellerCommentsItems.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          ) : (
            <p className="cr-comments">{vehicle.seller_comments || "No comments provided."}</p>
          )}
        </section>

        {/* ── TITLE INFORMATION ── */}
        {(titleStatus || titleState || titleBranding) && (
          <section className="cr-section">
            <h3 className="cr-section-bar">TITLE INFORMATION</h3>
            <div className="cr-condition-grid">
              {renderConditionField("Title Status", titleStatus)}
              {renderConditionField("Title State", titleState)}
              {renderConditionField("Title Branding", titleBranding)}
            </div>
          </section>
        )}

        {/* ── DAMAGE REPORT (from damage_items) ── */}
        {damageItems.length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">
              DAMAGE REPORT
              {damageSummary && <span className="cr-damage-count"> &mdash; {damageSummary.total_items ?? damageItems.length} item{(damageSummary.total_items ?? damageItems.length) !== 1 ? "s" : ""}</span>}
              {damageSummary?.structural_issue && <span className="cr-structural-flag"> STRUCTURAL ISSUE</span>}
            </h3>
            <table className="cr-damage-table">
              <thead>
                <tr>
                  <th>Section</th>
                  <th>Panel</th>
                  <th>Condition</th>
                  <th>Severity</th>
                </tr>
              </thead>
              <tbody>
                {damageItems.map((d, i) => (
                  <tr key={i}>
                    <td>{d.section_label || d.section || "—"}</td>
                    <td>{d.panel || "—"}</td>
                    <td>{d.condition || "—"}</td>
                    <td>
                      <span className={`cr-severity cr-severity-${d.severity_color || "gray"}`}>
                        {d.reported_severity || d.severity_label || "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {severitySummary && <p className="cr-comments" style={{ fontSize: 13, color: "#aaa" }}>{severitySummary}</p>}
          </section>
        )}

        {/* ── TIRE DEPTHS ── */}
        {tireDepths && Object.keys(tireDepths).length > 0 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">TIRE CONDITION</h3>
            <div className="cr-tire-grid">
              {Object.entries(tireDepths).map(([pos, tire]) => (
                <div key={pos} className="cr-tire-card">
                  <span className="cr-tire-pos">{tire.position_label || humanizeKey(pos)}</span>
                  <span className="cr-tire-depth">{tire.tread_depth || "N/A"}</span>
                  <span className="cr-tire-detail">{[tire.brand, tire.size].filter(Boolean).join(" · ") || ""}</span>
                  {tire.wheel_type && <span className="cr-tire-detail">{tire.wheel_type}</span>}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── VEHICLE HISTORY ── */}
        {vehicleHistory && (
          <section className="cr-section">
            <h3 className="cr-section-bar">VEHICLE HISTORY</h3>
            <div className="cr-kpi-row">
              {vehicleHistory.owners != null && (
                <div className="cr-kpi">
                  <span className="cr-kpi-label">Owners</span>
                  <span className="cr-kpi-value">{vehicleHistory.owners}</span>
                </div>
              )}
              {vehicleHistory.accidents != null && (
                <div className="cr-kpi">
                  <span className="cr-kpi-label">Accidents</span>
                  <span className="cr-kpi-value" style={vehicleHistory.accidents > 0 ? { color: "#e74c3c" } : undefined}>{vehicleHistory.accidents}</span>
                </div>
              )}
              <div className="cr-kpi">
                <span className="cr-kpi-label">Engine Starts</span>
                <span className="cr-kpi-value">{vehicleHistory.engine_starts === false ? "No" : "Yes"}</span>
              </div>
              <div className="cr-kpi">
                <span className="cr-kpi-label">Drivable</span>
                <span className="cr-kpi-value">{vehicleHistory.drivable === false ? "No" : "Yes"}</span>
              </div>
            </div>
          </section>
        )}

        {/* ── CONDITION DETAIL (structured fields — fallback for older reports) ── */}
        {hasStructuredData(report) && (
          <section className="cr-section">
            <h3 className="cr-section-bar">CONDITION DETAIL</h3>
            <div className="cr-condition-grid">
              {renderConditionField("Overall Grade", report.overall_grade)}
              {renderConditionField("Structural Damage", report.structural_damage)}
              {renderConditionField("Paint Condition", report.paint_condition)}
              {renderConditionField("Interior Condition", report.interior_condition)}
              {renderConditionField("Tire Condition", report.tire_condition)}
            </div>
          </section>
        )}

        {/* ── ADDITIONAL IMAGES ── */}
        {allImages.length > 8 && (
          <section className="cr-section">
            <h3 className="cr-section-bar">ADDITIONAL IMAGES</h3>
            <div className="cr-image-grid">
              {allImages.slice(8).map((img, i) => (
                <div key={i} className="cr-grid-thumb" onClick={() => setLightboxImage(img)}>
                  <img src={img} alt={`Image ${i + 9}`} onError={e => { e.currentTarget.src = FALLBACK_IMAGE; }} />
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── ORIGINAL CR BUTTON (bottom) ── */}
        {crUrl && (
          <section className="cr-section" style={{ textAlign: "center", padding: "20px 0" }}>
            <button className="button" onClick={() => window.open(crUrl, '_blank', 'noopener,noreferrer')} style={{ fontSize: 16, padding: "12px 32px" }}>
              See Original Condition Report
            </button>
          </section>
        )}
      </main>

      {/* ── IMAGE LIGHTBOX ── */}
      {lightboxImage && (
        <div className="cr-overlay" onClick={() => setLightboxImage(null)}>
          <button className="cr-overlay-close" onClick={() => setLightboxImage(null)}>×</button>
          <img src={lightboxImage} alt="Full size" className="cr-overlay-img" onClick={e => e.stopPropagation()} />
        </div>
      )}

      <style jsx>{`
        /* ── Layout ── */
        .cr-doc { max-width: 1200px; margin: 0 auto; }

        .cr-doc-header { background: var(--card-bg, #1a1a2e); padding: 16px 20px; border-radius: 8px; margin-bottom: 12px; }
        .cr-doc-header-inner { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .cr-doc-brand { margin: 0; font-size: 20px; }
        .cr-doc-header-actions { display: flex; gap: 8px; flex-wrap: wrap; }

        /* ── Section bars (like sample report) ── */
        .cr-section { margin-bottom: 16px; }
        .cr-section-bar {
          background: #2a2a3e;
          color: #e0e0e0;
          padding: 8px 14px;
          margin: 0 0 0 0;
          font-size: 14px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          border-left: 4px solid #c9a44a;
        }

        /* ── Details table (matches sample) ── */
        .cr-details-table { width: 100%; border-collapse: collapse; padding: 12px; }
        .cr-details-table td { padding: 6px 10px; font-size: 13px; }
        .cr-td-label { font-weight: 700; white-space: nowrap; color: #aaa; width: 100px; }

        /* ── Images layout (thumb column + hero + grade) ── */
        .cr-images-layout { display: flex; gap: 16px; padding: 14px; }
        .cr-thumb-col { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; width: 180px; flex-shrink: 0; }
        .cr-thumb { border: 1px solid #444; cursor: pointer; border-radius: 3px; overflow: hidden; }
        .cr-thumb:hover { border-color: #c9a44a; }
        .cr-thumb img { width: 100%; height: 55px; object-fit: cover; display: block; }
        .cr-hero-col { flex: 1; cursor: pointer; border: 1px solid #444; border-radius: 4px; overflow: hidden; }
        .cr-hero-col img { width: 100%; height: auto; max-height: 420px; object-fit: contain; display: block; }
        .cr-grade-col { width: 180px; flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; }
        .cr-grade-card { text-align: center; border: 2px solid #c9a44a; border-radius: 8px; padding: 16px 10px; }
        .cr-grade-label { display: block; font-size: 12px; color: #aaa; text-transform: uppercase; }
        .cr-grade-value { display: block; font-size: 36px; font-weight: 800; color: #c9a44a; margin: 4px 0; }
        .cr-grade-desc { display: block; font-size: 14px; color: #ccc; }
        .cr-grade-checks { list-style: disc; padding-left: 18px; font-size: 13px; margin: 0; }
        .cr-grade-checks li { margin-bottom: 4px; }

        /* ── KPI row ── */
        .cr-kpi-row { display: flex; gap: 12px; padding: 14px; flex-wrap: wrap; }
        .cr-kpi { flex: 1; min-width: 140px; border: 1px solid #444; border-radius: 6px; padding: 14px; text-align: center; }
        .cr-kpi-label { display: block; font-size: 11px; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .cr-kpi-value { display: block; font-size: 22px; font-weight: 700; }

        /* ── Announcements ── */
        .cr-announce-list { padding: 12px 12px 12px 30px; margin: 0; }
        .cr-empty { padding: 12px 14px; color: #7c7; margin: 0; }

        /* ── Comments ── */
        .cr-comments { padding: 12px 14px; margin: 0; }

        /* ── Problem highlights ── */
        .cr-problem-list li { color: #e7a33e; }

        /* ── Condition grid ── */
        .cr-condition-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 14px; }
        .cr-cond-item { display: flex; gap: 8px; }
        .cr-cond-label { font-weight: 700; color: #aaa; min-width: 140px; }

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

        /* ── Tire grid ── */
        .cr-tire-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 14px; }
        .cr-tire-card { border: 1px solid #444; border-radius: 6px; padding: 12px; text-align: center; }
        .cr-tire-pos { display: block; font-size: 11px; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .cr-tire-depth { display: block; font-size: 22px; font-weight: 700; color: #c9a44a; }
        .cr-tire-detail { display: block; font-size: 11px; color: #888; margin-top: 2px; }

        /* ── Image grid ── */
        .cr-image-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px; }
        .cr-grid-thumb { border: 1px solid #444; border-radius: 3px; overflow: hidden; cursor: pointer; }
        .cr-grid-thumb:hover { border-color: #c9a44a; }
        .cr-grid-thumb img { width: 100%; height: 120px; object-fit: cover; display: block; }

        /* ── Lightbox overlay ── */
        .cr-overlay {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.92);
          display: flex; align-items: center; justify-content: center;
          z-index: 10000;
        }
        .cr-overlay-close {
          position: fixed; top: 16px; right: 24px;
          background: none; border: none; color: #fff;
          font-size: 40px; cursor: pointer; z-index: 10001;
          line-height: 1; padding: 0;
        }
        .cr-overlay-close:hover { color: #c9a44a; }
        .cr-overlay-img { max-width: 92vw; max-height: 90vh; object-fit: contain; }

        @media print {
          .cr-doc-header-actions, .cr-overlay, .cr-iframe-overlay { display: none !important; }
        }

        @media (max-width: 768px) {
          .cr-images-layout { flex-direction: column; }
          .cr-thumb-col { width: 100%; grid-template-columns: repeat(4, 1fr); }
          .cr-grade-col { width: 100%; flex-direction: row; }
          .cr-kpi-row { flex-direction: column; }
          .cr-image-grid { grid-template-columns: repeat(2, 1fr); }
          .cr-tire-grid { grid-template-columns: repeat(2, 1fr); }
          .cr-damage-table { font-size: 12px; }
        }
      `}</style>
    </>
  );
}

/* ── Helpers ── */

function renderConditionField(label: string, value: unknown) {
  if (value === null || value === undefined) return null;
  return (
    <div className="cr-cond-item">
      <span className="cr-cond-label">{label}:</span>
      <span>{String(value)}</span>
    </div>
  );
}

function hasStructuredData(report: Record<string, unknown>): boolean {
  const fields = ["overall_grade", "structural_damage", "paint_condition", "interior_condition", "tire_condition"];
  return fields.some(f => report[f] !== null && report[f] !== undefined);
}

function resolveHeroImage(vehicle: VehicleDetail | null): string | null {
  if (!vehicle) return null;
  return (
    vehicle.hero_image ||
    vehicle.display_context?.hero_image ||
    (vehicle.display_images && vehicle.display_images[0]) ||
    (vehicle.images && vehicle.images[0]) ||
    null
  );
}

function stripSizeParam(url: string): string {
  try {
    const u = new URL(url);
    u.searchParams.delete("size");
    // Also strip ?size= variants without proper key-value (e.g., ?size=w86h64)
    const cleaned = u.toString().replace(/\?size=[^&]*&?/, "?").replace(/\?$/, "");
    return cleaned;
  } catch {
    return url.replace(/\?size=[^&]*/g, "");
  }
}

function resolveReportImages(vehicle: VehicleDetail | null): string[] {
  if (!vehicle) return [];

  // Prefer OVE detail images (actual CR photos, not Imagin Studio marketing)
  const oveImages = vehicle.ove_detail?.images || [];
  if (oveImages.length > 0) {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const entry of oveImages) {
      // images_json items are objects { url, role, ... } or plain strings
      const raw = typeof entry === "string" ? entry : (entry as { url?: string }).url;
      if (!raw || typeof raw !== "string") continue;
      // Skip non-photo assets (SVGs, logos, gifs)
      const lower = raw.toLowerCase();
      if (lower.includes(".svg") || lower.includes(".gif")) continue;
      const clean = stripSizeParam(raw);
      // Deduplicate by base URL (after stripping size)
      if (seen.has(clean)) continue;
      seen.add(clean);
      result.push(clean);
    }
    if (result.length > 0) return result;
  }

  // Fallback: gallery or raw images list
  return (
    vehicle.display_context?.gallery_images ||
    vehicle.display_images ||
    vehicle.images ||
    []
  );
}

function humanizeKey(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtMoney(value: number | null | undefined): string {
  if (!value) return "N/A";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(value);
}

function fmtMiles(value: number | null | undefined): string {
  if (!value) return "N/A";
  return new Intl.NumberFormat("en-US").format(value) + " mi";
}
