/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuctionSnapshotCard } from "@/components/AuctionSnapshotCard";
import { ConditionReportCard } from "@/components/ConditionReportCard";
import { apiFetch } from "@/lib/api";
import { AuthState, loadAuthState } from "@/lib/auth";

type DisplayMode = "MARKETING" | "INSPECTION_PENDING" | "INSPECTION_REPORT";
type InspectionStatus = "NOT_STARTED" | "PENDING" | "INGESTED" | "NORMALIZED" | "VERIFIED" | "FAILED";

type VehicleDisplayContext = {
  mode: DisplayMode;
  inspection_status: InspectionStatus;
  hero_image?: string | null;
  gallery_images?: string[];
  inspection_images?: string[];
  disclosure_images?: string[];
  has_inspection_report?: boolean;
  disclaimer?: string;
  condition_report?: Record<string, unknown>;
};

type VehicleDetail = {
  vin: string;
  listing_id?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  sub_body_type?: string | null;
  engine_type?: string | null;
  cylinders?: number | null;
  forced_induction?: string | null;
  drivetrain?: string | null;
  mpg_combined?: number | null;
  ev_range?: number | null;
  towing_capacity_lbs?: number | null;
  odometer?: number | null;
  condition_grade?: string | null;
  price_asking: number;
  price_wholesale_est?: number | null;
  location_zip?: string | null;
  location_state?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  images: string[];
  display_images?: string[];
  hero_image?: string | null;
  display_mode?: DisplayMode;
  inspection_status?: InspectionStatus;
  has_inspection_report?: boolean;
  display_context?: VehicleDisplayContext;
  source_label?: string | null;
  auction_house?: string | null;
  pickup_location?: string | null;
  inventory_status?: string | null;
  inventory_label?: string | null;
  condition_report_grade?: string | null;
  seller_comments?: string | null;
  condition_report?: Record<string, unknown>;
  listing_snapshot?: Record<string, unknown>;
  mmr?: number | null;
  features_raw: string[];
  features_normalized: Record<string, number>;
  available: boolean;
  last_seen_active?: string | null;
  updated_at?: string | null;
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

export function VehicleDetailPanel({ vin }: { vin: string }) {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setAuth(loadAuthState());
  }, []);

  useEffect(() => {
    async function loadVehicle() {
      setLoading(true);
      setError(null);
      const response = await apiFetch<VehicleDetail>(`/inventory/${encodeURIComponent(vin)}`);
      if (response.status !== "ok") {
        setVehicle(null);
        setSelectedImage(null);
        setError(response.error?.message || "Unable to load vehicle details.");
        setLoading(false);
        return;
      }
      setVehicle(response.data);
      const displayImages = resolveDisplayImages(response.data);
      setSelectedImage(resolveHeroImage(response.data) || displayImages[0] || null);
      setLoading(false);
    }

    void loadVehicle();
  }, [vin]);

  if (loading) {
    return (
      <div className="grid" style={{ gap: 12 }}>
        <Link className="button ghost" href={"/vinventory" as any}>
          Back to Inventory
        </Link>
        <section className="card">Loading vehicle details...</section>
      </div>
    );
  }

  if (error || !vehicle) {
    return (
      <div className="grid" style={{ gap: 12 }}>
        <Link className="button ghost" href={"/vinventory" as any}>
          Back to Inventory
        </Link>
        <section className="card">{error || "Vehicle not found."}</section>
      </div>
    );
  }

  const currentVehicle = vehicle;
  const displayImages = resolveDisplayImages(vehicle);
  const disclosureImages = vehicle.display_context?.disclosure_images || [];
  const inspectionEvidence = vehicle.display_context?.inspection_images || [];
  const conditionReport = vehicle.display_context?.condition_report || {};
  const primaryImage = selectedImage || resolveHeroImage(vehicle) || displayImages[0] || FALLBACK_IMAGE;

  async function addToGarage() {
    if (!auth?.accessToken) {
      setActionError("Sign in from VInventory before saving vehicles to My Garage.");
      setActionMessage(null);
      return;
    }

    setActionLoading("garage");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch<{
      ove_detail_refresh?: {
        queued?: boolean;
        deduplicated?: boolean;
      } | null;
    }>(`/me/garage/${encodeURIComponent(currentVehicle.vin)}`, { method: "POST" }, auth.accessToken);

    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to save vehicle to garage.");
      setActionLoading(null);
      return;
    }

    setActionMessage(
      response.data.ove_detail_refresh?.queued
        ? response.data.ove_detail_refresh.deduplicated
          ? "Vehicle saved. Auction detail refresh was already in progress."
          : "Vehicle saved. Auction detail refresh queued for the back office."
        : "Vehicle saved to My Garage."
    );
    setActionLoading(null);
  }

  async function startAcquisition() {
    if (!auth?.accessToken) {
      setActionError("Sign in from VInventory before starting acquisition.");
      setActionMessage(null);
      return;
    }

    setActionLoading("acquire");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch(
      `/me/garage/${encodeURIComponent(currentVehicle.vin)}/acquire`,
      { method: "POST" },
      auth.accessToken
    );
    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to start acquisition.");
      setActionLoading(null);
      return;
    }

    setActionMessage("Acquisition started. Redirecting to My Garage.");
    setActionLoading(null);
    window.location.href = `/dashboard?vin=${encodeURIComponent(currentVehicle.vin)}`;
  }

  async function requestConditionReport() {
    if (!auth?.accessToken) {
      setActionError("Sign in from VInventory before requesting a condition report.");
      setActionMessage(null);
      return;
    }

    setActionLoading("condition-report");
    setActionError(null);
    setActionMessage(null);
    const response = await apiFetch<{
      message?: string;
      already_available?: boolean;
    }>(
      `/me/vehicles/${encodeURIComponent(currentVehicle.vin)}/condition-report-request`,
      { method: "POST" },
      auth.accessToken
    );

    if (response.status !== "ok") {
      setActionError(response.error?.message || "Unable to request condition report.");
      setActionLoading(null);
      return;
    }

    setActionMessage(
      response.data.message ||
        (response.data.already_available
          ? "Condition report is already available for this vehicle."
          : "Condition report requested. Refresh this page after the scraper sync completes.")
    );
    setActionLoading(null);
  }

  return (
    <div className="grid" style={{ gap: 12 }}>
      <Link className="button ghost" href={"/vinventory" as any}>
        Back to Inventory
      </Link>

      <section className="card inventory-detail-top">
        <div>
          <h1 style={{ marginTop: 0, marginBottom: 8 }}>
            {vehicle.year} {vehicle.make} {vehicle.model}
          </h1>
          <p style={{ marginTop: 0 }}>
            {vehicle.trim || "Base"} | {vehicle.body_type || "Unknown"} | {vehicle.drivetrain || "N/A"}
          </p>
          <p style={{ marginBottom: 8 }}>
            <strong>${vehicle.price_asking.toLocaleString()}</strong> asking
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span className="badge">VIN {vehicle.vin}</span>
            <span className="badge">Source: {vehicle.source_label || vehicle.source_type || "unknown"}</span>
            <span className="badge">Condition: {vehicle.condition_grade || "N/A"}</span>
            <span className="badge">
              {vehicle.location_state || "NA"} {vehicle.location_zip || ""}
            </span>
            <span className="badge">{displayModeLabel(vehicle.display_mode || vehicle.display_context?.mode)}</span>
            <span className="badge">{inspectionStatusLabel(vehicle.inspection_status || vehicle.display_context?.inspection_status)}</span>
          </div>
        </div>

        <div className="inventory-detail-image">
          <img src={primaryImage} alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`} />
        </div>
      </section>

      {displayImages.length > 1 ? (
        <section className="card inventory-thumbnails">
          {displayImages.map((image) => (
            <button
              key={image}
              className={`inventory-thumb ${primaryImage === image ? "active" : ""}`}
              onClick={() => setSelectedImage(image)}
            >
              <img src={image} alt="Vehicle thumbnail" loading="lazy" />
            </button>
          ))}
        </section>
      ) : null}

      <section className="grid two">
        <article className="card">
          <h3>Vehicle Specs</h3>
          <p>Engine: {vehicle.engine_type || "N/A"}</p>
          <p>Cylinders: {vehicle.cylinders ?? "N/A"}</p>
          <p>Forced Induction: {vehicle.forced_induction || "N/A"}</p>
          <p>Mileage: {vehicle.odometer?.toLocaleString() || "N/A"}</p>
          <p>MPG Combined: {vehicle.mpg_combined ?? "N/A"}</p>
          <p>EV Range: {vehicle.ev_range ?? "N/A"}</p>
          <p>Towing Capacity: {vehicle.towing_capacity_lbs?.toLocaleString() || "N/A"} lbs</p>
          <p>Wholesale Estimate: {formatMoney(vehicle.price_wholesale_est)}</p>
        </article>

        <article className="card">
          <h3>Listing Metadata</h3>
          <p>Listing ID: {vehicle.listing_id || "N/A"}</p>
          <p>Available: {vehicle.available ? "Yes" : "No"}</p>
          <p>Last Seen Active: {formatDate(vehicle.last_seen_active)}</p>
          <p>Last Updated: {formatDate(vehicle.updated_at)}</p>
          <p>Display Mode: {displayModeLabel(vehicle.display_mode || vehicle.display_context?.mode)}</p>
          <p>Inspection Status: {inspectionStatusLabel(vehicle.inspection_status || vehicle.display_context?.inspection_status)}</p>
          <p>
            Source Priority:{" "}
            {vehicle.source_type === "ove" || vehicle.source_type === "auction"
              ? "Auction-grade inventory data (highest priority for overlapping VINs)"
              : "Retail and dealer feed data (overridden by auction-grade sources when VIN overlaps)"}
          </p>
          {vehicle.source_url ? (
            <p>
              Source URL:{" "}
              <a href={vehicle.source_url} target="_blank" rel="noreferrer">
                Open listing
              </a>
            </p>
          ) : null}
        </article>
      </section>

      {vehicle.display_context?.disclaimer ? (
        <section className="card">
          <h3>Image Source Notice</h3>
          <p style={{ marginBottom: 0 }}>{vehicle.display_context.disclaimer}</p>
        </section>
      ) : null}

      {vehicle.source_type === "ove" || vehicle.source_type === "auction" ? (
        <>
          <section className="inventory-actions">
            <button className="button" onClick={addToGarage} disabled={actionLoading !== null}>
              {actionLoading === "garage" ? "Saving..." : "Add to My Garage"}
            </button>
            <button className="button ghost" onClick={startAcquisition} disabled={actionLoading !== null}>
              {actionLoading === "acquire" ? "Starting..." : "Start Acquisition"}
            </button>
            {!vehicle.has_inspection_report ? (
              <button className="button ghost" onClick={requestConditionReport} disabled={actionLoading !== null}>
                {actionLoading === "condition-report" ? "Requesting..." : "Request Condition Report"}
              </button>
            ) : null}
            {vehicle.has_inspection_report ? (
              <Link className="button ghost" href={`/vinventory/${encodeURIComponent(vehicle.vin)}/condition-report` as any}>
                Open Condition Report
              </Link>
            ) : null}
          </section>
          {actionError ? <section className="card">{actionError}</section> : null}
          {actionMessage ? <section className="card">{actionMessage}</section> : null}
          <section className="grid two">
            <article className="card">
              <h3>Inspection Evidence</h3>
              <p>Inspection images: {inspectionEvidence.length}</p>
              <p>Disclosure images: {disclosureImages.length}</p>
              {disclosureImages.length ? (
                <div className="inventory-feature-grid">
                  {disclosureImages.map((image) => (
                    <a className="badge" key={image} href={image} target="_blank" rel="noreferrer">
                      Disclosure Photo
                    </a>
                  ))}
                </div>
              ) : (
                <p style={{ marginBottom: 0 }}>No disclosure photos provided.</p>
              )}
            </article>
            <ConditionReportCard
              report={vehicle.condition_report || conditionReport}
              grade={vehicle.condition_report_grade || vehicle.condition_grade}
              sellerComments={vehicle.seller_comments}
              auctionHouse={vehicle.auction_house}
              pickupLocation={vehicle.pickup_location}
              inventoryStatus={vehicle.inventory_status || vehicle.inventory_label}
              mmr={vehicle.mmr}
            />
          </section>
          <AuctionSnapshotCard snapshot={vehicle.listing_snapshot} />
        </>
      ) : null}

      <section className="card">
        <h3>Features</h3>
        {vehicle.features_raw.length ? (
          <div className="inventory-feature-grid">
            {vehicle.features_raw.slice(0, 24).map((feature) => (
              <span className="badge" key={feature}>
                {feature}
              </span>
            ))}
          </div>
        ) : (
          <p>No features listed.</p>
        )}
      </section>
    </div>
  );
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toLocaleString()}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString();
}

function resolveDisplayImages(vehicle: VehicleDetail | null | undefined): string[] {
  if (!vehicle) return [];
  const primary = vehicle.display_images || vehicle.display_context?.gallery_images || [];
  if (primary.length) return primary.filter(Boolean);
  return (vehicle.images || []).filter(Boolean);
}

function resolveHeroImage(vehicle: VehicleDetail | null | undefined): string | null {
  if (!vehicle) return null;
  return vehicle.hero_image || vehicle.display_context?.hero_image || null;
}

function displayModeLabel(mode: DisplayMode | undefined): string {
  if (mode === "INSPECTION_REPORT") return "Verified Inspection";
  if (mode === "INSPECTION_PENDING") return "Inspection Pending";
  return "Marketing Photos";
}

function inspectionStatusLabel(status: InspectionStatus | undefined): string {
  if (!status) return "Status Unknown";
  return `Inspection ${status.replaceAll("_", " ")}`;
}
