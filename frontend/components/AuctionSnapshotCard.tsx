"use client";

type AuctionSnapshotCardProps = {
  snapshot?: Record<string, unknown> | null;
  title?: string;
};

export function AuctionSnapshotCard({ snapshot, title = "Auction Listing Snapshot" }: AuctionSnapshotCardProps) {
  const data = snapshot || {};
  const badges = toObjectList(data.badges);
  const heroFacts = toObjectList(data.hero_facts).filter((item) => {
    // Filter out hero facts whose value is a JSON blob or extremely long raw text
    const val = typeof item.value === "string" ? item.value.trim() : "";
    if (val.startsWith("{") || val.startsWith("[") || val.startsWith("<")) return false;
    if (val.length > 200) return false;
    return true;
  });
  const icons = toObjectList(data.icons).filter((item) => {
    // Filter out icons that are SVG/image assets with no useful textual content
    if (item.kind === "svg" || item.kind === "image") return false;
    const name = typeof item.name === "string" ? item.name.trim() : "";
    const val = typeof item.value === "string" ? item.value.trim() : "";
    return Boolean(name || val);
  });
  const sections = toObjectList(data.sections);

  if (
    !data.title &&
    !data.subtitle &&
    !badges.length &&
    !heroFacts.length &&
    !icons.length &&
    !sections.length &&
    !data.page_url
  ) {
    return null;
  }

  return (
    <article className="card">
      <h3>{title}</h3>
      {typeof data.title === "string" ? (
        <p style={{ marginBottom: 4 }}>
          <strong>{data.title}</strong>
        </p>
      ) : null}
      {typeof data.subtitle === "string" ? <p style={{ marginTop: 0 }}>{data.subtitle}</p> : null}

      {badges.length ? (
        <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
          {badges.map((item, index) => (
            <span className="badge" key={`${item.label || "badge"}-${index}`}>
              {toDisplayText(item.label, toDisplayText(item.value, "Badge"))}
            </span>
          ))}
        </div>
      ) : null}

      {heroFacts.length ? (
        <>
          <h4 style={{ marginBottom: 8 }}>Hero Facts</h4>
          <div className="inventory-modal-data-grid">
            {heroFacts.map((item, index) => (
              <div className="vinv-modal-data-row" key={`${item.label || "fact"}-${index}`}>
                <span>{toDisplayText(item.label, "Fact")}</span>
                <strong>{toDisplayText(item.value, "N/A")}</strong>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {icons.length ? (
        <>
          <h4 style={{ marginBottom: 8 }}>Auction Facts</h4>
          <div className="inventory-modal-data-grid">
            {icons.map((item, index) => (
              <div className="vinv-modal-data-row" key={`${item.name || "icon"}-${index}`}>
                <span>{toDisplayText(item.name, "Fact")}</span>
                <strong>{toDisplayText(item.value, "N/A")}</strong>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {sections.length ? (
        <div className="grid" style={{ gap: 12 }}>
          {sections.map((section, index) => (
            <div
              key={`${toDisplayText(section.id, toDisplayText(section.title, "section"))}-${index}`}
              className="inventory-modal-specs"
            >
              <strong>{toDisplayText(section.title, toDisplayText(section.id, "Section"))}</strong>
              {Array.isArray(section.items) && section.items.length ? (
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {section.items.map((item, itemIndex) => (
                    <li key={itemIndex}>{describeSectionItem(item)}</li>
                  ))}
                </ul>
              ) : (
                <p style={{ marginBottom: 0 }}>No section items available.</p>
              )}
            </div>
          ))}
        </div>
      ) : null}

      {typeof data.page_url === "string" && data.page_url ? (
        <p style={{ marginBottom: 0 }}>
          <a href={data.page_url} target="_blank" rel="noreferrer">
            Open source auction page
          </a>
        </p>
      ) : null}
    </article>
  );
}

function toObjectList(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
}

function describeSectionItem(value: unknown): string {
  if (!value || typeof value !== "object") return "Detail unavailable";
  const item = value as Record<string, unknown>;
  const parts = [item.label, item.value, item.text]
    .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0);
  return parts.length ? parts.join(": ") : JSON.stringify(item);
}

function toDisplayText(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) {
    const text = value.trim();
    // Reject raw JSON blobs, SVG/HTML markup, or excessively long values
    if (text.startsWith("{") || text.startsWith("[") || text.startsWith("<")) return fallback;
    if (text.length > 200) return text.slice(0, 200) + "\u2026";
    return text;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}
