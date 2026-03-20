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

type ConditionReportCardProps = {
  report?: Record<string, unknown> | null;
  grade?: string | null;
  sellerComments?: string | null;
  auctionHouse?: string | null;
  pickupLocation?: string | null;
  inventoryStatus?: string | null;
  mmr?: number | null;
  title?: string;
};

export function ConditionReportCard({
  report,
  grade,
  sellerComments,
  auctionHouse,
  pickupLocation,
  inventoryStatus,
  mmr,
  title = "VCH Condition Report",
}: ConditionReportCardProps) {
  const normalizedReport = report || {};
  const announcements = toStringList(normalizedReport.announcements);
  const problemHighlights = toStringList(normalizedReport.problem_highlights);
  const damageItems = Array.isArray(normalizedReport.damage_items) ? (normalizedReport.damage_items as DamageItem[]) : [];
  const damageSummary = normalizedReport.damage_summary as DamageSummary | undefined;
  const vehicleHistory = normalizedReport.vehicle_history as VehicleHistory | undefined;
  const aiSummary = typeof normalizedReport.ai_summary === "string" ? normalizedReport.ai_summary : null;

  // Primitive highlights — exclude keys that are rendered as dedicated sections
  const RICH_KEYS = new Set(["announcements", "remarks", "seller_comments_items", "problem_highlights", "damage_items", "damage_summary", "tire_depths", "vehicle_history", "severity_summary", "ai_summary", "metadata", "raw_text"]);
  const highlights = collectPrimitiveEntries(normalizedReport).filter(([, , key]) => !RICH_KEYS.has(key));

  const hasAnyContent = announcements.length > 0 || problemHighlights.length > 0 || highlights.length > 0 || sellerComments || damageItems.length > 0 || vehicleHistory || aiSummary;

  return (
    <article className="card">
      <h3>{title}</h3>
      <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
        {grade ? <span className="badge">Grade {grade}</span> : null}
        {auctionHouse ? <span className="badge">{auctionHouse}</span> : null}
        {pickupLocation ? <span className="badge">{pickupLocation}</span> : null}
        {inventoryStatus ? <span className="badge">Status {inventoryStatus}</span> : null}
        {mmr !== null && mmr !== undefined ? <span className="badge">MMR {formatMoney(mmr)}</span> : null}
        {damageSummary?.structural_issue && <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>Structural Issue</span>}
        {vehicleHistory?.accidents != null && vehicleHistory.accidents > 0 && (
          <span className="badge" style={{ background: "#e74c3c", color: "#fff" }}>{vehicleHistory.accidents} Accident{vehicleHistory.accidents !== 1 ? "s" : ""}</span>
        )}
      </div>

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
      {aiSummary && <p style={{ marginTop: 0, fontSize: 13, color: "#ccc" }}>{aiSummary}</p>}

      {sellerComments ? <p style={{ marginTop: 0 }}>Seller Comments: {sellerComments}</p> : null}

      {announcements.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Announcements</h4>
          <ul style={{ marginTop: 0, paddingLeft: 20 }}>
            {announcements.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </>
      )}

      {/* Damage summary */}
      {damageItems.length > 0 && (
        <>
          <h4 style={{ marginBottom: 8 }}>Damage ({damageSummary?.total_items ?? damageItems.length} items)</h4>
          <div style={{ fontSize: 13 }}>
            {damageItems.slice(0, 5).map((d, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid #333" }}>
                <span>{d.panel || d.section_label || d.section || "—"}</span>
                <span style={{ color: severityColor(d.severity_color), fontWeight: 600, fontSize: 12 }}>
                  {d.severity_label || d.reported_severity || "—"}
                </span>
              </div>
            ))}
            {damageItems.length > 5 && <p style={{ fontSize: 12, color: "#888", margin: "4px 0 0" }}>+{damageItems.length - 5} more items</p>}
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
