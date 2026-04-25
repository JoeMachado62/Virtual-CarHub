"use client";

type DamageItem = {
  section?: string;
  section_label?: string;
  panel?: string;
  condition?: string;
  reported_severity?: string;
  severity_color?: string;
  severity_label?: string;
};

type DamageSummary = {
  total_items?: number;
  by_color?: Record<string, number>;
  by_section?: Record<string, number>;
  structural_issue?: boolean;
};

type VehicleHistory = {
  engine_starts?: boolean;
  drivable?: boolean;
  owners?: number;
  accidents?: number;
};

type AutoCheckReport = {
  scrape_status?: string;
  autocheck_score?: number | null;
  owner_count?: number | null;
  accident_count?: number | null;
  title_brand_check?: string | null;
  odometer_check?: string | null;
  accident_check?: string | null;
  vehicle_use?: string | null;
};

type ConditionReportCardProps = {
  report?: Record<string, unknown> | null;
  grade?: string | null;
  sellerComments?: string | null;
  pickupLocation?: string | null;
  inventoryStatus?: string | null;
  mmr?: number | null;
  title?: string;
};

export function ConditionReportCard({
  report,
  grade,
  sellerComments,
  pickupLocation,
  inventoryStatus,
  mmr,
  title = "VirtualCarHub Inspection Report",
}: ConditionReportCardProps) {
  const normalizedReport = report || {};
  const announcements = toStringList(normalizedReport.announcements).filter((item) => !containsMarketplaceMention(item));
  const problemHighlights = toStringList(normalizedReport.problem_highlights).filter((item) => !containsMarketplaceMention(item));
  const equipmentFeatures = toStringList(normalizedReport.equipment_features).filter((item) => !containsMarketplaceMention(item));
  const highValueOptions = Array.isArray(normalizedReport.high_value_options) ? normalizedReport.high_value_options as Array<Record<string, unknown>> : [];
  const damageItems = Array.isArray(normalizedReport.damage_items) ? (normalizedReport.damage_items as DamageItem[]) : [];
  const damageSummary = normalizedReport.damage_summary as DamageSummary | undefined;
  const vehicleHistory = normalizedReport.vehicle_history as VehicleHistory | undefined;
  const autoCheck = normalizeAutoCheck(normalizedReport.autocheck);
  const aiSummary = typeof normalizedReport.ai_summary === "string" && !containsMarketplaceMention(normalizedReport.ai_summary)
    ? normalizedReport.ai_summary
    : null;
  const sanitizedSellerComments = sanitizeMarketplaceCopy(sellerComments);
  const locationBadge = formatPickupLocation(pickupLocation);

  // Primitive highlights — exclude keys that are rendered as dedicated sections
  const RICH_KEYS = new Set([
    "announcements", "remarks", "seller_comments_items", "problem_highlights",
    "damage_items", "damage_summary", "tire_depths", "vehicle_history",
    "severity_summary", "ai_summary", "metadata", "raw_text",
    "equipment_features", "installed_equipment", "high_value_options",
    "autocheck", "inspection", "mechanical_findings", "diagnostic_codes",
    // Suppress fields already shown on the VDP or redundant with other CR sections
    "exterior_color", "interior_color", "exterior_color_oem_name",
    "exterior_paint_code", "exterior_color_rgb", "has_prior_paint",
    "overall_grade", "paint_condition", "title_status", "title_state", "title_branding",
  ]);
  const highlights = collectPrimitiveEntries(normalizedReport)
    .filter(([, value, key]) => !RICH_KEYS.has(key) && !containsMarketplaceMention(value));

  // Inspection issue counts from structured NAAA inspection data
  const inspection = normalizedReport.inspection as Record<string, { label: string; issue_count: number }> | undefined;
  const inspectionSections = inspection
    ? ["drivability", "exterior", "interior", "mechanical", "tires"]
        .map((id) => inspection[id])
        .filter(Boolean)
    : [];
  const totalIssues = inspectionSections.reduce((sum, s) => sum + (s.issue_count || 0), 0);

  const hasAnyContent = announcements.length > 0 || problemHighlights.length > 0 || highlights.length > 0 || sanitizedSellerComments || damageItems.length > 0 || vehicleHistory || aiSummary || equipmentFeatures.length > 0 || highValueOptions.length > 0 || Boolean(autoCheck) || inspectionSections.length > 0;

  return (
    <article className="card">
      <h3>{title}</h3>
      <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
        {grade ? <span className="badge">Grade {grade}</span> : null}
        {locationBadge ? <span className="badge">{locationBadge}</span> : null}
        {inventoryStatus ? <span className="badge">Status {inventoryStatus}</span> : null}
        {mmr !== null && mmr !== undefined ? <span className="badge">MMR {formatMoney(mmr)}</span> : null}
        {damageSummary?.structural_issue && <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>Structural Issue</span>}
        {vehicleHistory?.accidents != null && vehicleHistory.accidents > 0 && (
          <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>{vehicleHistory.accidents} Accident{vehicleHistory.accidents !== 1 ? "s" : ""}</span>
        )}
        {totalIssues > 0 && (
          <span className="badge" style={{ background: "#e7a33e", color: "#fff" }}>{totalIssues} Inspection Issue{totalIssues !== 1 ? "s" : ""}</span>
        )}
      </div>

      {/* NAAA Inspection Issue Summary */}
      {inspectionSections.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4, marginBottom: 12, fontSize: 11 }}>
          {inspectionSections.map((s) => (
            <div key={s.label} style={{ textAlign: "center", padding: "4px 2px", background: s.issue_count > 0 ? "rgba(231,76,60,0.15)" : "var(--surface-soft)", borderRadius: 4, border: `1px solid ${s.issue_count > 0 ? "rgba(231,76,60,0.4)" : "var(--line)"}` }}>
              <div style={{ fontWeight: 700, color: s.issue_count > 0 ? "var(--danger)" : "var(--mint)", fontSize: 16 }}>{s.issue_count}</div>
              <div style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.3px", lineHeight: 1.2 }}>
                {s.label.replace("Mechanical & Diagnostic Trouble Codes", "Mechanical").replace("Drivability, Keys, & History", "Drivability").replace("Tires & Wheels", "Tires")}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Problem highlights — top priority summary */}
      {problemHighlights.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Problem Highlights</h4>
          <ul style={{ marginTop: 0, paddingLeft: 20, color: "#e7a33e" }}>
            {problemHighlights.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </>
      )}

      {/* AI summary */}
      {aiSummary && <p style={{ marginTop: 0, fontSize: 13, color: "var(--muted)" }}>{aiSummary}</p>}

      {sanitizedSellerComments ? <p style={{ marginTop: 0 }}>Vehicle Notes: {sanitizedSellerComments}</p> : null}

      {announcements.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Announcements</h4>
          <ul style={{ marginTop: 0, paddingLeft: 20 }}>
            {announcements.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      )}

      {(equipmentFeatures.length > 0 || highValueOptions.length > 0) && (
        <>
          <h4 style={{ marginBottom: 8 }}>{equipmentFeatures.length > 0 ? "Equipment & Features" : "High Value Options"}</h4>
          <div className="inventory-feature-grid" style={{ gap: 6 }}>
            {equipmentFeatures.slice(0, 12).map((item) => <span className="badge" key={item}>{item}</span>)}
            {highValueOptions.slice(0, 8).map((item, index) => {
              const label = typeof item.primary_description === "string" ? item.primary_description : null;
              if (!label) return null;
              return <span className="badge" key={`${label}-${index}`}>{label}</span>;
            })}
          </div>
        </>
      )}

      {/* Damage summary */}
      {damageItems.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Damage ({damageSummary?.total_items ?? damageItems.length} items)</h4>
          <div style={{ fontSize: 13 }}>
            {damageItems.slice(0, 5).map((d, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--line)" }}>
                <span>{d.panel || d.section_label || d.section || "—"}</span>
                <span style={{ color: severityColor(d.severity_color), fontWeight: 600, fontSize: 12 }}>
                  {d.severity_label || d.reported_severity || "—"}
                </span>
              </div>
            ))}
            {damageItems.length > 5 && <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 0" }}>+{damageItems.length - 5} more items</p>}
          </div>
        </>
      )}

      {/* Vehicle history */}
      {vehicleHistory && (
        <div className="inventory-feature-grid" style={{ marginTop: 8, gap: 6 }}>
          {vehicleHistory.owners != null && <span className="badge">Owners: {vehicleHistory.owners}</span>}
          {vehicleHistory.engine_starts === false && <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>Engine: No Start</span>}
          {vehicleHistory.drivable === false && <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>Not Drivable</span>}
        </div>
      )}

      {autoCheck && (
        <>
          <h4 style={{ marginBottom: 8 }}>AutoCheck History</h4>
          {autoCheck.scrape_status === "failed" ? (
            <p style={{ marginTop: 0, color: "var(--muted)" }}>AutoCheck data is temporarily unavailable.</p>
          ) : (
            <>
              <div className="inventory-feature-grid" style={{ gap: 6 }}>
                {autoCheck.autocheck_score != null ? <span className="badge">AutoCheck Score: {autoCheck.autocheck_score}</span> : null}
                {autoCheck.owner_count != null ? <span className="badge">Owners: {autoCheck.owner_count}</span> : null}
                {autoCheck.accident_count != null ? (
                  <span
                    className="badge"
                    style={autoCheck.accident_count > 0 ? { background: "#e74c3c", color: "#fff" } : undefined}
                  >
                    Accidents: {autoCheck.accident_count}
                  </span>
                ) : null}
                {autoCheck.title_brand_check ? <span className="badge">Title Brand: {autoCheck.title_brand_check}</span> : null}
                {autoCheck.odometer_check ? <span className="badge">Odometer: {autoCheck.odometer_check}</span> : null}
              </div>
              <div className="inventory-modal-data-grid" style={{ marginTop: 10 }}>
                {renderAutoCheckRow("Accident Check", autoCheck.accident_check)}
                {renderAutoCheckRow("Vehicle Use", autoCheck.vehicle_use)}
              </div>
            </>
          )}
        </>
      )}

      {highlights.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Report Highlights</h4>
          <div className="inventory-modal-data-grid">
            {highlights.map(([label, value]) => (
              <div className="vinv-modal-data-row" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </>
      )}

      {!hasAnyContent ? (
        <p style={{ marginBottom: 0 }}>Condition report data is not yet available.</p>
      ) : null}
    </article>
  );
}

function containsMarketplaceMention(value: string | null | undefined): boolean {
  const text = (value || "").toLowerCase();
  return /\b(manheim|adesa|traderev|smartauction|openlane|ove\.com|acv auctions|backlotcars)\b/.test(text);
}

function sanitizeMarketplaceCopy(value: string | null | undefined): string | null {
  if (!value) return null;
  let cleaned = value;
  // Strip phone numbers, emails, URLs
  cleaned = cleaned.replace(/(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g, "");
  cleaned = cleaned.replace(/[\w.+-]+@[\w.-]+\.\w{2,}/g, "");
  cleaned = cleaned.replace(/https?:\/\/[^\s,)]+/gi, "");
  cleaned = cleaned.replace(/www\.[^\s,)]+/gi, "");
  // Strip auction house names
  cleaned = cleaned.replace(/\b(Manheim|ADESA|TradeRev|SmartAuction|Smart Auction|Ally\s+Smart\s*Auction|OPENLANE|OVE\.com|ACV\s+Auctions|ACV|BacklotCars|Backlot\s+Cars)\b/gi, "");
  // Split into sentences and filter any that still mention marketplace
  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .filter((sentence) => !containsMarketplaceMention(sentence));
  const sanitized = sentences.join(" ").replace(/\s{2,}/g, " ").trim();
  return sanitized || null;
}

function formatPickupLocation(value: string | null | undefined): string | null {
  const text = (value || "").trim();
  if (!text || containsMarketplaceMention(text)) return null;
  const match = text.match(/^([A-Z]{2})\s*-\s*(.+)$/);
  if (!match) return text;
  const state = match[1];
  const city = match[2]
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
  return `${city}, ${state}`;
}

function collectPrimitiveEntries(report: Record<string, unknown>): Array<[string, string, string]> {
  return Object.entries(report).flatMap(([key, value]) => {
    if (value === null || value === undefined || value === "") return [];
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return [[humanizeKey(key), String(value), key]];
    }
    if (Array.isArray(value) && value.every((item) => typeof item === "string" || typeof item === "number")) {
      return [[humanizeKey(key), value.join(", "), key]];
    }
    return [];
  });
}

function humanizeKey(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function formatMoney(value: number): string {
  return `$${value.toLocaleString()}`;
}

function severityColor(color?: string): string {
  switch (color) {
    case "red": return "#e74c3c";
    case "yellow": return "#e7a33e";
    case "green": return "#7c7";
    default: return "#aaa";
  }
}

function normalizeAutoCheck(value: unknown): AutoCheckReport | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  return {
    scrape_status: typeof raw.scrape_status === "string" ? raw.scrape_status : undefined,
    autocheck_score: toFiniteNumber(raw.autocheck_score),
    owner_count: toFiniteNumber(raw.owner_count),
    accident_count: toFiniteNumber(raw.accident_count),
    title_brand_check: normalizeText(raw.title_brand_check),
    odometer_check: normalizeText(raw.odometer_check),
    accident_check: normalizeText(raw.accident_check),
    vehicle_use: normalizeText(raw.vehicle_use),
  };
}

function normalizeText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.round(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.round(parsed);
  }
  return null;
}

function renderAutoCheckRow(label: string, value: string | null | undefined) {
  if (!value) return null;
  return (
    <div className="vinv-modal-data-row" key={label}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
