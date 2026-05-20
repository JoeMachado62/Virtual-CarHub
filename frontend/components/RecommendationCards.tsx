/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";

import { maskVin } from "@/lib/vin";

export type Recommendation = {
  vin: string;
  public_slug?: string | null;
  status?: string;
  match_score: number;
  explainability: string;
  market_retail: number;
  target_acquisition: number;
  estimated_otd: number;
  danny_savings: number;
  last_seen_active?: string | null;
  vehicle: {
    year: number;
    make: string;
    model: string;
    trim?: string;
    odometer?: number;
    price: number;
    location?: string;
    images?: string[];
    thumbnail?: string | null;
  };
};

const FALLBACK_IMAGE = "/assets/images/portfolio/VCH Auction default image.webp";
const SHOWROOM_BG = "/assets/images/portfolio/vch-showroom.webp";

const EXTERIOR_SHOT_CODES = new Set(["01", "02", "03", "05", "06", "07"]);

function extractShotCode(url: string): string | null {
  const ccMatch = url.match(/cc_\w+_(\d{2})_\d+/);
  if (ccMatch) return ccMatch[1];
  const match = url.match(/_(\d{2})\.\w{3,4}$/);
  return match ? match[1] : null;
}

function isChromeDataExterior(url: string | null | undefined): boolean {
  if (!url || !url.includes("media.chromedata.com")) return false;
  const shot = extractShotCode(url);
  return !shot || EXTERIOR_SHOT_CODES.has(shot);
}

export function RecommendationCards({
  data,
  onSelect,
  onFavorite,
  isAdmin = false,
  maxVisible = 4
}: {
  data: Recommendation[];
  onSelect: (vin: string) => Promise<void>;
  onFavorite: (vin: string) => Promise<void>;
  isAdmin?: boolean;
  maxVisible?: number;
}) {
  if (!data.length) {
    return <div className="card">No recommendations yet. Complete Quick Match first.</div>;
  }

  const visible = data.slice(0, maxVisible);
  const hiddenCount = Math.max(data.length - visible.length, 0);

  return (
    <>
      <div className="grid two recommendation-grid">
        {visible.map((item) => {
          const isSelected = item.status === "selected";
          const title = `${item.vehicle.year || ""} ${item.vehicle.make || ""} ${item.vehicle.model || ""}`.trim();
          const chromeDataImage = isChromeDataExterior(item.vehicle.thumbnail) ? item.vehicle.thumbnail : null;
          const imageUrl = chromeDataImage || FALLBACK_IMAGE;
          const detailHref = `/vinventory/${encodeURIComponent(item.public_slug || item.vin)}` as `/vinventory/${string}`;

          return (
            <article className="card recommendation-card" key={item.vin}>
              <Link
                className={`recommendation-media${chromeDataImage ? " is-studio" : ""}`}
                href={detailHref}
                aria-label={`View ${title || item.vin}`}
                style={chromeDataImage ? { background: `url(${SHOWROOM_BG}) center bottom / cover no-repeat` } : undefined}
              >
                <img
                  src={imageUrl}
                  alt={title || "Recommended vehicle"}
                  className={chromeDataImage ? "recommendation-studio-img" : undefined}
                />
              </Link>
              <div className="recommendation-copy">
                <div className="recommendation-head">
                  <strong>{title || item.vin}</strong>
                  <span className="badge">Score {(item.match_score * 100).toFixed(0)}%</span>
                </div>
                <p style={{ marginBottom: 8 }}>{item.explainability}</p>
                <p className="recommendation-price">Price ${item.vehicle.price?.toLocaleString()}</p>
                <p>OTD ${item.estimated_otd?.toLocaleString()} | Danny Savings ${item.danny_savings?.toLocaleString()}</p>
                <p>VIN: {maskVin(item.vin, isAdmin)}</p>
                {item.last_seen_active ? <p className="dashboard-muted-note">Last active {formatDate(item.last_seen_active)}</p> : null}
                <div className="recommendation-actions">
                  <button className="button" onClick={() => onSelect(item.vin)} disabled={isSelected}>
                    {isSelected ? "Selected" : "Select Vehicle"}
                  </button>
                  <button className="button ghost" onClick={() => onFavorite(item.vin)}>
                    {item.status === "favorited" ? "Favorited" : "Favorite"}
                  </button>
                  <Link className="button secondary" href={detailHref}>
                    View Details
                  </Link>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {hiddenCount ? (
        <p className="dashboard-muted-note recommendation-count-note">
          Showing the top {visible.length} fresh matches. {hiddenCount} more kept out of this shortlist.
        </p>
      ) : null}
    </>
  );
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
