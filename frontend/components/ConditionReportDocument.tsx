/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";
import { toPublicSourceLabel } from "@/lib/sourceLabels";

type VehicleDetail = {
  vin: string;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
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
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

export function ConditionReportDocument({ vin }: { vin: string }) {
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const report = useMemo(
    () => vehicle?.condition_report || vehicle?.display_context?.condition_report || {},
    [vehicle]
  );
  const reportEntries = useMemo(
    () => collectPrimitiveEntries(report).filter(([key]) => key !== "announcements"),
    [report]
  );
  const announcements = useMemo(() => toStringList(report.announcements), [report]);
  const listingSections = useMemo(() => toObjectList(vehicle?.listing_snapshot?.sections), [vehicle]);
  const heroFacts = useMemo(() => toObjectList(vehicle?.listing_snapshot?.hero_facts), [vehicle]);
  const inspectionImages = vehicle?.display_context?.inspection_images || [];
  const disclosureImages = vehicle?.display_context?.disclosure_images || [];
  const galleryImages = resolveReportImages(vehicle);
  const primaryImage = resolveHeroImage(vehicle) || galleryImages[0] || FALLBACK_IMAGE;
  const hasConditionReport = Boolean(vehicle && (vehicle.condition_report || vehicle.display_context?.condition_report));

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
    <main className="page-stack condition-report-shell">
      <section className="section-shell page-hero compact">
        <div className="condition-report-header">
          <div>
            <p className="section-eyebrow">Client Report</p>
            <h1 style={{ marginBottom: 8 }}>
              {vehicle.year} {vehicle.make} {vehicle.model}
            </h1>
            <p className="muted-copy" style={{ marginBottom: 0 }}>
              VIN {vehicle.vin} | {toPublicSourceLabel(vehicle.source_label, vehicle.source_type)} | Updated{" "}
              {formatDate(vehicle.updated_at)}
            </p>
          </div>
          <div className="condition-report-actions">
            <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vehicle.vin)}` as any}>
              Back to Vehicle
            </Link>
            <button className="button" onClick={() => window.print()}>
              Print Report
            </button>
          </div>
        </div>
      </section>

      {!hasConditionReport ? (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Condition Report Pending</h2>
          <p style={{ marginBottom: 0 }}>
            A full inspection report has not been ingested for this vehicle yet. The auction detail request can still
            be queued from VInventory or the internal PI console.
          </p>
        </section>
      ) : null}

      <section className="condition-report-grid">
        <article className="card">
          <h2 style={{ marginTop: 0 }}>Vehicle Summary</h2>
          <div className="inventory-modal-data-grid">
            <div className="vinv-modal-data-row">
              <span>Vehicle</span>
              <strong>
                {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim || ""}
              </strong>
            </div>
            <div className="vinv-modal-data-row">
              <span>Pricing</span>
              <strong>{formatMoney(vehicle.price_asking)}</strong>
            </div>
            <div className="vinv-modal-data-row">
              <span>Condition Grade</span>
              <strong>{vehicle.condition_report_grade || vehicle.condition_grade || "Pending"}</strong>
            </div>
            <div className="vinv-modal-data-row">
              <span>MMR</span>
              <strong>{formatMoney(vehicle.mmr)}</strong>
            </div>
            <div className="vinv-modal-data-row">
              <span>Location</span>
              <strong>{`${vehicle.location_state || "NA"} ${vehicle.location_zip || ""}`.trim()}</strong>
            </div>
            <div className="vinv-modal-data-row">
              <span>Pickup</span>
              <strong>{vehicle.pickup_location || "Not provided"}</strong>
            </div>
          </div>
        </article>

        <article className="card">
          <h2 style={{ marginTop: 0 }}>Auction Context</h2>
          <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
            {vehicle.auction_house ? <span className="badge">{vehicle.auction_house}</span> : null}
            {vehicle.inventory_status || vehicle.inventory_label ? (
              <span className="badge">Status {vehicle.inventory_status || vehicle.inventory_label}</span>
            ) : null}
            {vehicle.body_type ? <span className="badge">{vehicle.body_type}</span> : null}
            {vehicle.drivetrain ? <span className="badge">{vehicle.drivetrain}</span> : null}
          </div>
          <p>Mileage: {formatMiles(vehicle.odometer)}</p>
          <p>Seller comments: {vehicle.seller_comments || "None captured."}</p>
          {vehicle.source_url ? (
            <p style={{ marginBottom: 0 }}>
              Source listing:{" "}
              <a href={vehicle.source_url} target="_blank" rel="noreferrer">
                Open source page
              </a>
            </p>
          ) : (
            <p style={{ marginBottom: 0 }}>Source listing URL not available.</p>
          )}
        </article>
      </section>

      {announcements.length ? (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Announcements</h2>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {announcements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {reportEntries.length ? (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Condition Detail</h2>
          <div className="inventory-modal-data-grid">
            {reportEntries.map(([label, value]) => (
              <div className="vinv-modal-data-row" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {heroFacts.length || listingSections.length ? (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Auction Listing Notes</h2>
          {heroFacts.length ? (
            <div className="inventory-modal-data-grid" style={{ marginBottom: listingSections.length ? 16 : 0 }}>
              {heroFacts.map((item, index) => (
                <div className="vinv-modal-data-row" key={`${item.label || "fact"}-${index}`}>
                  <span>{toDisplayText(item.label, "Fact")}</span>
                  <strong>{toDisplayText(item.value, "N/A")}</strong>
                </div>
              ))}
            </div>
          ) : null}
          {listingSections.length ? (
            <div className="condition-report-grid">
              {listingSections.map((section, index) => (
                <div className="inventory-modal-specs" key={`${toDisplayText(section.id, "section")}-${index}`}>
                  <strong>{toDisplayText(section.title, toDisplayText(section.id, "Section"))}</strong>
                  {Array.isArray(section.items) && section.items.length ? (
                    <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                      {section.items.map((item, itemIndex) => (
                        <li key={itemIndex}>{describeSectionItem(item)}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No auction notes were captured for this section.</p>
                  )}
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Vehicle Imaging</h2>
        {vehicle.display_context?.disclaimer ? <p>{vehicle.display_context.disclaimer}</p> : null}
        <div className="condition-report-gallery">
          <a className="condition-report-gallery-card" href={primaryImage} target="_blank" rel="noreferrer">
            <img src={primaryImage} alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`} />
            <strong>Primary image</strong>
          </a>
          {inspectionImages.map((image, index) => (
            <a
              className="condition-report-gallery-card"
              href={image}
              key={`inspection-${index}`}
              target="_blank"
              rel="noreferrer"
            >
              <img src={image} alt={`Inspection evidence ${index + 1}`} />
              <strong>Inspection image {index + 1}</strong>
            </a>
          ))}
          {disclosureImages.map((image, index) => (
            <a
              className="condition-report-gallery-card"
              href={image}
              key={`disclosure-${index}`}
              target="_blank"
              rel="noreferrer"
            >
              <img src={image} alt={`Disclosure image ${index + 1}`} />
              <strong>Disclosure image {index + 1}</strong>
            </a>
          ))}
        </div>
      </section>
    </main>
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

function resolveReportImages(vehicle: VehicleDetail | null): string[] {
  if (!vehicle) return [];
  const images = vehicle.display_images || vehicle.display_context?.gallery_images || vehicle.images || [];
  return images.filter(Boolean);
}

function resolveHeroImage(vehicle: VehicleDetail | null): string | null {
  if (!vehicle) return null;
  return vehicle.hero_image || vehicle.display_context?.hero_image || null;
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function toObjectList(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
}

function toDisplayText(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function describeSectionItem(value: unknown): string {
  if (!value || typeof value !== "object") return "Detail unavailable";
  const item = value as Record<string, unknown>;
  const parts = [item.label, item.value, item.text]
    .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0);
  return parts.length ? parts.join(": ") : JSON.stringify(item);
}

function humanizeKey(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toLocaleString()}`;
}

function formatMiles(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return value.toLocaleString();
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}
