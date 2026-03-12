"use client";

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
  const highlights = collectPrimitiveEntries(normalizedReport).filter(([key]) => key !== "announcements");

  return (
    <article className="card">
      <h3>{title}</h3>
      <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
        {grade ? <span className="badge">Grade {grade}</span> : null}
        {auctionHouse ? <span className="badge">{auctionHouse}</span> : null}
        {pickupLocation ? <span className="badge">{pickupLocation}</span> : null}
        {inventoryStatus ? <span className="badge">Status {inventoryStatus}</span> : null}
        {mmr !== null && mmr !== undefined ? <span className="badge">MMR {formatMoney(mmr)}</span> : null}
      </div>

      {sellerComments ? <p style={{ marginTop: 0 }}>Seller Comments: {sellerComments}</p> : null}

      {announcements.length ? (
        <>
          <h4 style={{ marginBottom: 8 }}>Announcements</h4>
          <ul style={{ marginTop: 0, paddingLeft: 20 }}>
            {announcements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {highlights.length ? (
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
      ) : null}

      {!announcements.length && !highlights.length && !sellerComments ? (
        <p style={{ marginBottom: 0 }}>Condition report data is not yet available.</p>
      ) : null}
    </article>
  );
}

function collectPrimitiveEntries(report: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(report).flatMap(([key, value]) => {
    if (value === null || value === undefined || value === "") return [];
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return [[humanizeKey(key), String(value)]];
    }
    if (Array.isArray(value) && value.every((item) => typeof item === "string" || typeof item === "number")) {
      return [[humanizeKey(key), value.join(", ")]];
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
