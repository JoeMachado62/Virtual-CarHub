/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";

type HotDealItem = {
  id: string;
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  price_asking: number;
  location_state?: string | null;
  thumbnail?: string | null;
  mmr_value: number;
  deal_delta: number;
  deal_delta_pct?: number | null;
  deal_label: string;
  auction_end_at: string;
  marketing_title?: string | null;
  marketing_summary?: string | null;
  vdp_path: string;
  reference_pending?: boolean;
  dealer_photos_gated?: boolean;
  gated_photo_count?: number;
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

function formatCountdown(target: string, now: number) {
  const end = new Date(target).getTime();
  const remaining = Math.max(0, end - now);
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

export function HotDealsPreview() {
  const [items, setItems] = useState<HotDealItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    async function loadPreview() {
      const response = await apiFetch<{ items: HotDealItem[] }>("/inventory/hot-deals/active?limit=12");

      if (response.status !== "ok") {
        setError(response.error?.message || "Unable to load Hot Deals.");
        return;
      }

      setItems(response.data.items || []);
    }

    void loadPreview();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const pendingReferenceVins = useMemo(
    () => items.filter((item) => item.reference_pending && !item.thumbnail).map((item) => item.vin),
    [items],
  );

  useEffect(() => {
    if (pendingReferenceVins.length === 0) return;

    let cancelled = false;
    async function fetchReferenceBatch() {
      try {
        const response = await apiFetch<{ results: Record<string, { hero_url: string; gallery_urls: string[] }> }>(
          "/inventory/reference-images/batch",
          { method: "POST", body: JSON.stringify({ vins: pendingReferenceVins.slice(0, 10) }) },
        );
        if (cancelled || response.status !== "ok" || !response.data?.results) return;
        const results = response.data.results;
        setItems((prev) =>
          prev.map((item) => {
            const reference = results[item.vin];
            if (!reference?.hero_url) return item;
            return { ...item, thumbnail: reference.hero_url, reference_pending: false };
          }),
        );
      } catch {
        // Reference media is nice-to-have; keep the safe fallback if it is unavailable.
      }
    }

    void fetchReferenceBatch();
    return () => { cancelled = true; };
  }, [pendingReferenceVins]);

  const featured = items[0];
  const remaining = useMemo(() => items.slice(1), [items]);

  if (error) {
    return <div className="hot-deals-empty">{error}</div>;
  }

  if (!items.length) {
    return (
      <div className="hot-deals-empty">
        <strong>Hot Deals are loading.</strong>
        <span>Fresh screened opportunities will appear here as soon as the VHC Marketing List posts.</span>
      </div>
    );
  }

  return (
    <div className="hot-deals-board">
      {featured ? (
        <article className="hot-deal-card hot-deal-card--featured">
          <div className="hot-deal-media">
            <img src={featured.thumbnail || FALLBACK_IMAGE} alt={`${featured.year} ${featured.make} ${featured.model}`} />
            <span className="hot-deal-countdown">{formatCountdown(featured.auction_end_at, now)}</span>
          </div>
          <div className="hot-deal-copy">
            <div className="hot-deal-topline">
              <span className="hot-deal-pill">Deal of the Hour</span>
              <span className="hot-deal-badge">{featured.deal_label} Deal</span>
            </div>
            <h3>
              {featured.year} {featured.make} {featured.model}
            </h3>
            <p>{featured.trim || "VHC Marketing List"} • {featured.location_state || "Nationwide"}</p>
            <div className="hot-deal-stats">
              <strong>{formatMoney(featured.price_asking)}</strong>
              <span>{formatMoney(featured.deal_delta)} below MMR</span>
            </div>
            <Link href={featured.vdp_path as any} className="button hot-deal-action">
              View Hot Deal
            </Link>
          </div>
        </article>
      ) : null}

      {remaining.length ? (
        <div className="hot-deals-scroll" aria-label="More Hot Deals">
          {remaining.map((item) => (
            <article key={item.id} className="hot-deal-card hot-deal-card--compact">
              <div className="hot-deal-media">
                <img src={item.thumbnail || FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} />
                <span className="hot-deal-countdown">{formatCountdown(item.auction_end_at, now)}</span>
              </div>
              <div className="hot-deal-copy">
                <div className="hot-deal-topline">
                  <span className="hot-deal-badge">{item.deal_label} Deal</span>
                  <span>{formatMoney(item.deal_delta)} below</span>
                </div>
                <h3>
                  {item.year} {item.make} {item.model}
                </h3>
                <p>{formatMoney(item.price_asking)} • {item.location_state || "Nationwide"}</p>
                <Link href={item.vdp_path as any} className="button ghost">
                  View
                </Link>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
