/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { toPublicSourceLabel } from "@/lib/sourceLabels";

type PreviewItem = {
  vin: string;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  price_asking: number;
  location_state?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  thumbnail?: string | null;
  images_count?: number;
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

export function InventoryPreview() {
  const [items, setItems] = useState<PreviewItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadPreview() {
      const response = await apiFetch<{ items: PreviewItem[] }>(
        "/inventory/search?source_type=auction&has_images=false&page=1&per_page=3"
      );

      if (response.status !== "ok") {
        setError(response.error?.message || "Unable to load inventory preview.");
        return;
      }

      setItems(response.data.items || []);
    }

    void loadPreview();
  }, []);

  if (error) {
    return <div className="card">{error}</div>;
  }

  if (!items.length) {
    return <div className="card">Loading live auction inventory...</div>;
  }

  return (
    <div className="preview-grid">
      {items.map((item) => (
        <article key={item.vin} className="preview-card">
          <img
            src={item.thumbnail || FALLBACK_IMAGE}
            alt={`${item.year} ${item.make} ${item.model}`}
            className="preview-image"
          />
          <div className="preview-copy">
            <div className="preview-row">
              <strong>
                {item.year} {item.make} {item.model}
              </strong>
              <span className="badge">{toPublicSourceLabel(item.source_label, item.source_type)}</span>
            </div>
            <p>{item.trim || "Auction listing"} </p>
            <p>
              ${item.price_asking.toLocaleString()} • {item.location_state || "Nationwide"}
            </p>
            <Link href={`/vinventory/${encodeURIComponent(item.vin)}` as any} className="button ghost">
              View Vehicle
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}
