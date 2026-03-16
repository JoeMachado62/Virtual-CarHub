function normalizeSourceKey(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function titleize(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function normalizeSourceFilterValue(value: string | null | undefined): string {
  const normalized = normalizeSourceKey(value);
  if (normalized === "ove" || normalized === "auction") return "auction";
  if (normalized === "marketcheck" || normalized === "dealer_wholesale" || normalized === "wholesale") {
    return "wholesale";
  }
  return normalized;
}

export function toPublicSourceLabel(primary: string | null | undefined, fallback?: string | null | undefined): string {
  const normalized = normalizeSourceKey(primary || fallback);
  if (!normalized) return "Inventory";
  if (normalized === "auction" || normalized === "ove") return "Auction";
  if (normalized === "wholesale" || normalized === "marketcheck" || normalized === "dealer_wholesale") {
    return "Wholesale";
  }
  if (normalized === "dealer_partner") return "Dealer Partner Choice";
  return titleize(normalized);
}

export function formatAuctionPlatformLabel(value: string | null | undefined): string {
  const normalized = normalizeSourceKey(value);
  if (!normalized) return "Unknown";
  if (normalized === "manheim") return "Primary Auction Feed";
  if (normalized === "openlane") return "OPENLANE";
  if (normalized === "ally_smart_auction") return "SmartAuction";
  return titleize(normalized);
}
