/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";
import { AuthState, clearAuthState, loadAuthState, saveAuthState } from "@/lib/auth";

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

type InventoryItem = {
  vin: string;
  listing_id?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  body_type?: string | null;
  drivetrain?: string | null;
  price_asking: number;
  odometer?: number | null;
  location_state?: string | null;
  location_zip?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  thumbnail?: string | null;
  images_count?: number;
  features_preview?: string[];
  display_mode?: DisplayMode;
  inspection_status?: InspectionStatus;
  has_inspection_report?: boolean;
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
  features_raw: string[];
  features_normalized: Record<string, number>;
  available: boolean;
  last_seen_active?: string | null;
  updated_at?: string | null;
};

type Pagination = {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
};

type SyncMeta = {
  requested: boolean;
  enabled: boolean;
  executed: boolean;
  mode: string;
  fetched: number;
  inserted: number;
  updated: number;
  skipped_priority: number;
  skipped_invalid: number;
  error?: string | null;
};

type InventorySearchPayload = {
  items: InventoryItem[];
  pagination: Pagination;
  sync?: SyncMeta;
};

type GarageItem = {
  id: string;
  vin: string;
  status: string;
  source: string;
  added_at: string;
  updated_at: string;
  acquisition_started_at?: string | null;
  deal_stage: string;
  vehicle: {
    year?: number | null;
    make?: string | null;
    model?: string | null;
    trim?: string | null;
    price_asking?: number | null;
    odometer?: number | null;
    location_state?: string | null;
    location_zip?: string | null;
    source_type?: string | null;
    thumbnail?: string | null;
  };
};

type FilterState = {
  q: string;
  make: string;
  model: string;
  body_type: string;
  source_type: string;
  state: string;
  min_price: string;
  max_price: string;
  min_year: string;
  max_year: string;
  min_miles: string;
  max_miles: string;
  has_images: boolean;
  live_sync: boolean;
  sort_by: "updated_at" | "price_asking" | "year" | "odometer";
  sort_dir: "asc" | "desc";
};

const INITIAL_FILTERS: FilterState = {
  q: "",
  make: "",
  model: "",
  body_type: "",
  source_type: "",
  state: "",
  min_price: "",
  max_price: "",
  min_year: "",
  max_year: "",
  min_miles: "",
  max_miles: "",
  has_images: false,
  live_sync: true,
  sort_by: "updated_at",
  sort_dir: "desc",
};

const EMPTY_PAGINATION: Pagination = {
  page: 1,
  per_page: 18,
  total: 0,
  total_pages: 0,
  has_next: false,
  has_prev: false,
};

const EMPTY_SYNC: SyncMeta = {
  requested: false,
  enabled: false,
  executed: false,
  mode: "disabled",
  fetched: 0,
  inserted: 0,
  updated: 0,
  skipped_priority: 0,
  skipped_invalid: 0,
  error: null,
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

export function InventoryExplorer() {
  const searchParams = useSearchParams();
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authEmail, setAuthEmail] = useState("buyer@example.com");
  const [authPassword, setAuthPassword] = useState("BuyerPass123!");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<InventoryItem[]>([]);
  const [pagination, setPagination] = useState<Pagination>(EMPTY_PAGINATION);
  const [syncMeta, setSyncMeta] = useState<SyncMeta>(EMPTY_SYNC);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedVin, setSelectedVin] = useState<string | null>(null);
  const [detailsByVin, setDetailsByVin] = useState<Record<string, VehicleDetail>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const [garageItems, setGarageItems] = useState<GarageItem[]>([]);
  const [garageLoading, setGarageLoading] = useState(false);
  const [garageActionVin, setGarageActionVin] = useState<string | null>(null);
  const [garageError, setGarageError] = useState<string | null>(null);

  useEffect(() => {
    const saved = loadAuthState();
    if (saved) {
      setAuth(saved);
      if (saved.email) setAuthEmail(saved.email);
    }
  }, []);

  useEffect(() => {
    const q = searchParams.get("q") || "";
    const sourceType = searchParams.get("source_type") || "";
    if (!q && !sourceType) return;

    const nextFilters = {
      ...INITIAL_FILTERS,
      q,
      source_type: sourceType,
    };
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
  }, [searchParams]);

  useEffect(() => {
    void loadInventory(appliedFilters, page);
  }, [appliedFilters, page]);

  useEffect(() => {
    if (auth?.accessToken) {
      void loadGarage(auth.accessToken);
    } else {
      setGarageItems([]);
      setGarageError(null);
    }
  }, [auth?.accessToken]);

  useEffect(() => {
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeModal();
      }
    }
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, []);

  async function login() {
    setAuthLoading(true);
    setAuthError(null);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: authEmail, password: authPassword }),
    });
    if (response.status !== "ok") {
      setAuthError(response.error?.message || "Unable to sign in.");
      setAuthLoading(false);
      return;
    }

    const nextAuth: AuthState = {
      userId: response.data.user_id,
      email: authEmail,
      accessToken: response.data.access_token,
      refreshToken: response.data.refresh_token,
    };
    setAuth(nextAuth);
    saveAuthState(nextAuth);
    setAuthLoading(false);
  }

  function signOut() {
    clearAuthState();
    setAuth(null);
  }

  async function loadInventory(currentFilters: FilterState, currentPage: number) {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (currentFilters.q.trim()) params.set("q", currentFilters.q.trim());
    if (currentFilters.make.trim()) params.set("make", currentFilters.make.trim());
    if (currentFilters.model.trim()) params.set("model", currentFilters.model.trim());
    if (currentFilters.body_type.trim()) params.set("body_type", currentFilters.body_type.trim());
    if (currentFilters.source_type.trim()) params.set("source_type", currentFilters.source_type.trim());
    if (currentFilters.state.trim()) params.set("state", currentFilters.state.trim().toUpperCase());
    if (currentFilters.min_price.trim()) params.set("min_price", currentFilters.min_price.trim());
    if (currentFilters.max_price.trim()) params.set("max_price", currentFilters.max_price.trim());
    if (currentFilters.min_year.trim()) params.set("min_year", currentFilters.min_year.trim());
    if (currentFilters.max_year.trim()) params.set("max_year", currentFilters.max_year.trim());
    if (currentFilters.min_miles.trim()) params.set("min_miles", currentFilters.min_miles.trim());
    if (currentFilters.max_miles.trim()) params.set("max_miles", currentFilters.max_miles.trim());
    params.set("has_images", currentFilters.has_images ? "true" : "false");
    params.set("live_sync", currentFilters.live_sync ? "true" : "false");
    params.set("sync_limit", "72");
    params.set("sort_by", currentFilters.sort_by);
    params.set("sort_dir", currentFilters.sort_dir);
    params.set("page", String(currentPage));
    params.set("per_page", "18");

    const response = await apiFetch<InventorySearchPayload>(`/inventory/search?${params.toString()}`);
    if (response.status !== "ok") {
      setRows([]);
      setPagination(EMPTY_PAGINATION);
      setSyncMeta(EMPTY_SYNC);
      setError(response.error?.message || "Failed to load inventory.");
      setLoading(false);
      return;
    }

    setRows(response.data.items || []);
    setPagination(response.data.pagination || EMPTY_PAGINATION);
    setSyncMeta(response.data.sync || EMPTY_SYNC);
    setLoading(false);
  }

  async function loadGarage(accessToken: string) {
    setGarageLoading(true);
    setGarageError(null);
    const response = await apiFetch<GarageItem[]>("/me/garage", {}, accessToken);
    if (response.status !== "ok") {
      setGarageItems([]);
      setGarageError(response.error?.message || "Unable to load garage.");
      setGarageLoading(false);
      return;
    }
    setGarageItems(response.data || []);
    setGarageLoading(false);
  }

  function submitFilters(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({ ...filters });
  }

  function resetFilters() {
    setFilters(INITIAL_FILTERS);
    setAppliedFilters(INITIAL_FILTERS);
    setPage(1);
  }

  async function openVehicleModal(vin: string) {
    setSelectedVin(vin);
    setDetailError(null);

    const cached = detailsByVin[vin];
    if (cached) {
      const cachedImages = resolveDisplayImages(cached);
      setSelectedImage(resolveHeroImage(cached) || cachedImages[0] || null);
      return;
    }

    setDetailLoading(true);
    const response = await apiFetch<VehicleDetail>(`/inventory/${encodeURIComponent(vin)}`);
    if (response.status !== "ok") {
      setDetailError(response.error?.message || "Unable to load vehicle details.");
      setDetailLoading(false);
      return;
    }

    setDetailsByVin((prev) => ({ ...prev, [vin]: response.data }));
    const nextImages = resolveDisplayImages(response.data);
    setSelectedImage(resolveHeroImage(response.data) || nextImages[0] || null);
    setDetailLoading(false);
  }

  function closeModal() {
    setSelectedVin(null);
    setDetailError(null);
    setDetailLoading(false);
    setSelectedImage(null);
  }

  function requireAuthForGarageAction(): AuthState | null {
    if (!auth?.accessToken) {
      setGarageError("Sign in to save vehicles to your account-wide garage.");
      return null;
    }
    return auth;
  }

  async function addToGarage(vin: string) {
    const session = requireAuthForGarageAction();
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    const response = await apiFetch<GarageItem>(`/me/garage/${encodeURIComponent(vin)}`, { method: "POST" }, session.accessToken);
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to save vehicle to garage.");
      setGarageActionVin(null);
      return;
    }
    setGarageItems((prev) => {
      const remaining = prev.filter((item) => item.vin !== response.data.vin);
      return [response.data, ...remaining];
    });
    setGarageActionVin(null);
  }

  async function removeFromGarage(vin: string) {
    const session = requireAuthForGarageAction();
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    const response = await apiFetch<{ vin: string; status: string }>(
      `/me/garage/${encodeURIComponent(vin)}`,
      { method: "DELETE" },
      session.accessToken
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to remove vehicle from garage.");
      setGarageActionVin(null);
      return;
    }
    setGarageItems((prev) => prev.filter((item) => item.vin !== vin));
    setGarageActionVin(null);
  }

  async function startAcquisition(vin: string) {
    const session = requireAuthForGarageAction();
    if (!session) return;
    setGarageActionVin(vin);
    setGarageError(null);
    const response = await apiFetch<{
      garage_item: GarageItem;
      deal: { id: string; stage: string; selected_vin: string };
    }>(`/me/garage/${encodeURIComponent(vin)}/acquire`, { method: "POST" }, session.accessToken);
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to start acquisition.");
      setGarageActionVin(null);
      return;
    }

    setGarageItems((prev) => {
      const remaining = prev.filter((item) => item.vin !== response.data.garage_item.vin);
      return [response.data.garage_item, ...remaining];
    });
    setGarageActionVin(null);
    window.location.href = `/dashboard?vin=${encodeURIComponent(vin)}`;
  }

  const pageButtons = useMemo(() => {
    const pages: number[] = [];
    const start = Math.max(1, pagination.page - 2);
    const end = Math.min(pagination.total_pages, pagination.page + 2);
    for (let value = start; value <= end; value += 1) pages.push(value);
    return pages;
  }, [pagination.page, pagination.total_pages]);

  const selectedVehicle = selectedVin ? detailsByVin[selectedVin] : null;
  const selectedVehicleImages = resolveDisplayImages(selectedVehicle);
  const selectedVehiclePrimaryImage = selectedImage || resolveHeroImage(selectedVehicle) || selectedVehicleImages[0] || null;
  const garageVins = useMemo(() => new Set(garageItems.map((item) => item.vin)), [garageItems]);

  return (
    <>
      <div className="inventory-layout">
        <aside className="card inventory-sidebar">
          <div className="inventory-sidebar-head">
            <h2>Filter Vehicles</h2>
            <span className="badge">CarGurus-style search</span>
          </div>

          {!auth?.accessToken ? (
            <section className="card" style={{ padding: 12, marginBottom: 10 }}>
              <h3 style={{ marginTop: 0 }}>Account Login</h3>
              <p style={{ marginTop: 0 }}>Sign in to save vehicles in your account garage.</p>
              <label>
                Email
                <input className="input" value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} />
              </label>
              <label>
                Password
                <input
                  className="input"
                  type="password"
                  value={authPassword}
                  onChange={(event) => setAuthPassword(event.target.value)}
                />
              </label>
              {authError ? <p style={{ color: "#b42318", marginBottom: 0 }}>{authError}</p> : null}
              <div className="inventory-actions" style={{ marginTop: 10 }}>
                <button className="button" onClick={login} disabled={authLoading}>
                  {authLoading ? "Signing in..." : "Sign In"}
                </button>
              </div>
            </section>
          ) : (
            <section className="card" style={{ padding: 12, marginBottom: 10 }}>
              <p style={{ marginTop: 0, marginBottom: 8 }}>
                Signed in as <strong>{auth.email || "buyer"}</strong>
              </p>
              <div className="inventory-actions">
                <button className="button ghost" onClick={() => loadGarage(auth.accessToken)} disabled={garageLoading}>
                  Refresh Garage
                </button>
                <button className="button ghost" onClick={signOut}>
                  Sign Out
                </button>
              </div>
            </section>
          )}

          <form onSubmit={submitFilters} className="inventory-filter-form">
            <label>
              Search
              <input
                className="input"
                placeholder="VIN, make, model, trim"
                value={filters.q}
                onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
              />
            </label>

            <div className="inventory-mini-grid">
              <label>
                Make
                <input
                  className="input"
                  value={filters.make}
                  onChange={(event) => setFilters((prev) => ({ ...prev, make: event.target.value }))}
                />
              </label>
              <label>
                Model
                <input
                  className="input"
                  value={filters.model}
                  onChange={(event) => setFilters((prev) => ({ ...prev, model: event.target.value }))}
                />
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                Min Price
                <input
                  className="input"
                  type="number"
                  value={filters.min_price}
                  onChange={(event) => setFilters((prev) => ({ ...prev, min_price: event.target.value }))}
                />
              </label>
              <label>
                Max Price
                <input
                  className="input"
                  type="number"
                  value={filters.max_price}
                  onChange={(event) => setFilters((prev) => ({ ...prev, max_price: event.target.value }))}
                />
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                Min Year
                <input
                  className="input"
                  type="number"
                  value={filters.min_year}
                  onChange={(event) => setFilters((prev) => ({ ...prev, min_year: event.target.value }))}
                />
              </label>
              <label>
                Max Year
                <input
                  className="input"
                  type="number"
                  value={filters.max_year}
                  onChange={(event) => setFilters((prev) => ({ ...prev, max_year: event.target.value }))}
                />
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                Min Miles
                <input
                  className="input"
                  type="number"
                  value={filters.min_miles}
                  onChange={(event) => setFilters((prev) => ({ ...prev, min_miles: event.target.value }))}
                />
              </label>
              <label>
                Max Miles
                <input
                  className="input"
                  type="number"
                  value={filters.max_miles}
                  onChange={(event) => setFilters((prev) => ({ ...prev, max_miles: event.target.value }))}
                />
              </label>
            </div>

            <div className="inventory-mini-grid">
              <label>
                Body Type
                <input
                  className="input"
                  placeholder="SUV, Truck, Sedan..."
                  value={filters.body_type}
                  onChange={(event) => setFilters((prev) => ({ ...prev, body_type: event.target.value }))}
                />
              </label>
              <label>
                State
                <input
                  className="input"
                  maxLength={2}
                  placeholder="FL"
                  value={filters.state}
                  onChange={(event) => setFilters((prev) => ({ ...prev, state: event.target.value }))}
                />
              </label>
            </div>

            <label>
              Source
              <select
                className="select"
                value={filters.source_type}
                onChange={(event) => setFilters((prev) => ({ ...prev, source_type: event.target.value }))}
              >
                <option value="">Any Source</option>
                <option value="ove">OVE / Manheim</option>
                <option value="auction">Auction</option>
                <option value="marketcheck">MarketCheck</option>
                <option value="dealer_partner">Dealer Partner</option>
                <option value="dealer_wholesale">Dealer Wholesale</option>
              </select>
            </label>

            <div className="inventory-mini-grid">
              <label>
                Sort By
                <select
                  className="select"
                  value={filters.sort_by}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, sort_by: event.target.value as FilterState["sort_by"] }))
                  }
                >
                  <option value="updated_at">Recently Updated</option>
                  <option value="price_asking">Price</option>
                  <option value="year">Year</option>
                  <option value="odometer">Mileage</option>
                </select>
              </label>
              <label>
                Direction
                <select
                  className="select"
                  value={filters.sort_dir}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, sort_dir: event.target.value as FilterState["sort_dir"] }))
                  }
                >
                  <option value="desc">Descending</option>
                  <option value="asc">Ascending</option>
                </select>
              </label>
            </div>

            <label className="inventory-toggle">
              <input
                type="checkbox"
                checked={filters.has_images}
                onChange={(event) => setFilters((prev) => ({ ...prev, has_images: event.target.checked }))}
              />
              Only show vehicles with photos
            </label>

            <label className="inventory-toggle">
              <input
                type="checkbox"
                checked={filters.live_sync}
                onChange={(event) => setFilters((prev) => ({ ...prev, live_sync: event.target.checked }))}
              />
              Trigger live MarketCheck sync on search
            </label>

            <div className="inventory-actions">
              <button className="button" type="submit" disabled={loading}>
                {loading ? "Searching..." : "Search"}
              </button>
              <button className="button ghost" type="button" onClick={resetFilters} disabled={loading}>
                Reset
              </button>
            </div>
          </form>
        </aside>

        <section className="inventory-main">
          <header className="card inventory-results-header">
            <div>
              <h3 style={{ marginTop: 0, marginBottom: 6 }}>Vehicle Listings</h3>
              <p style={{ margin: 0 }}>
                {pagination.total.toLocaleString()} matches | Page {pagination.page} of{" "}
                {Math.max(pagination.total_pages, 1)}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span className="badge">Garage: {garageItems.length}</span>
              {syncMeta.requested ? (
                <span className="badge">
                  Sync {syncMeta.executed ? syncMeta.mode : "pending"} | +{syncMeta.inserted} new / {syncMeta.updated} upd
                </span>
              ) : (
                <span className="badge">Local DB search</span>
              )}
              <Link className="button ghost" href="/">
                Back Home
              </Link>
            </div>
          </header>

          {syncMeta.error ? <div className="card">MarketCheck sync warning: {syncMeta.error}</div> : null}
          {error ? <div className="card">{error}</div> : null}
          {!error && loading ? <div className="card">Loading inventory...</div> : null}
          {!loading && !error && rows.length === 0 ? (
            <div className="card">No vehicles match your current filters.</div>
          ) : null}

          {!loading && !error && rows.length > 0 ? (
            <div className="inventory-grid">
              {rows.map((item) => (
                <article className="card inventory-card" key={item.vin}>
                  <Link className="inventory-media-button" href={`/vinventory/${encodeURIComponent(item.vin)}` as any}>
                    <div className="inventory-media">
                      {item.thumbnail ? (
                        <img src={item.thumbnail} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      ) : (
                        <img src={FALLBACK_IMAGE} alt={`${item.year} ${item.make} ${item.model}`} loading="lazy" />
                      )}
                    </div>
                  </Link>
                  <div className="inventory-card-body">
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <strong>
                        {item.year} {item.make} {item.model}
                      </strong>
                      <span className="badge">{item.source_type || "unknown"}</span>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="badge">{displayModeLabel(item.display_mode)}</span>
                      <span className="badge">{inspectionStatusLabel(item.inspection_status)}</span>
                    </div>

                    <p className="inventory-price">${item.price_asking.toLocaleString()}</p>
                    <p style={{ margin: 0 }}>
                      {item.trim || "Base"} | {item.body_type || "Unknown"} | {item.drivetrain || "N/A"}
                    </p>
                    <p style={{ margin: 0 }}>
                      {formatMiles(item.odometer)} miles | {item.location_state || "NA"} {item.location_zip || ""}
                    </p>
                    <p style={{ margin: 0 }}>VIN: {item.vin}</p>
                    <p className="inventory-description">
                      {item.features_preview?.length
                        ? item.features_preview.join(" • ")
                        : item.source_type === "ove"
                          ? "Auction listing with live pricing. Condition reports unlock as the buyer workflow advances."
                          : "Market-backed listing with synced specs and media."}
                    </p>

                    <div className="inventory-actions">
                      <Link className="button" href={`/vinventory/${encodeURIComponent(item.vin)}` as any}>
                        View Details
                      </Link>
                      <button className="button ghost" onClick={() => openVehicleModal(item.vin)}>
                        Quick View
                      </button>
                      <button
                        className="button ghost"
                        onClick={() => addToGarage(item.vin)}
                        disabled={garageVins.has(item.vin) || garageActionVin === item.vin}
                      >
                        {garageActionVin === item.vin ? "Saving..." : garageVins.has(item.vin) ? "In Garage" : "Add to My Garage"}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {pagination.total_pages > 1 ? (
            <section className="card inventory-pagination">
              <button
                className="button ghost"
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={!pagination.has_prev || loading}
              >
                Previous
              </button>
              {pageButtons.map((value) => (
                <button
                  key={value}
                  className={`button ${value === pagination.page ? "" : "ghost"}`}
                  onClick={() => setPage(value)}
                  disabled={loading}
                >
                  {value}
                </button>
              ))}
              <button
                className="button ghost"
                onClick={() => setPage((prev) => prev + 1)}
                disabled={!pagination.has_next || loading}
              >
                Next
              </button>
            </section>
          ) : null}

          <section className="card inventory-garage">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <h3 style={{ margin: 0 }}>My Garage</h3>
              <span className="badge">{garageItems.length} saved</span>
            </div>
            {garageError ? <p style={{ color: "#b42318", margin: 0 }}>{garageError}</p> : null}
            {garageLoading ? <p style={{ margin: 0 }}>Loading garage...</p> : null}
            {!garageLoading && !garageItems.length ? (
              <p style={{ marginBottom: 0 }}>Save vehicles here to persist by account and deal.</p>
            ) : (
              <div className="inventory-garage-grid">
                {garageItems.map((item) => (
                  <article key={item.id} className="inventory-garage-item">
                    <div>
                      <strong>{garageItemTitle(item)}</strong>
                      <p style={{ margin: 0 }}>
                        {formatMoney(item.vehicle.price_asking)} | {garageItemLocation(item)}
                      </p>
                      <p style={{ margin: 0 }}>VIN: {item.vin}</p>
                      <p style={{ margin: 0 }}>Status: {item.status}</p>
                    </div>
                    <div className="inventory-actions">
                      <Link className="button ghost" href={`/vinventory/${encodeURIComponent(item.vin)}` as any}>
                        Open
                      </Link>
                      <button
                        className="button"
                        onClick={() => startAcquisition(item.vin)}
                        disabled={garageActionVin === item.vin}
                      >
                        {garageActionVin === item.vin ? "Starting..." : "Start Acquisition"}
                      </button>
                      <button
                        className="button ghost"
                        onClick={() => removeFromGarage(item.vin)}
                        disabled={garageActionVin === item.vin}
                      >
                        Remove
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </section>
      </div>

      {selectedVin ? (
        <div className="inventory-modal-overlay" onClick={closeModal}>
          <section
            className="card inventory-modal"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="inventory-modal-header">
              <h3 style={{ margin: 0 }}>Vehicle Detail</h3>
              <button className="button ghost" onClick={closeModal}>
                Close
              </button>
            </header>

            {detailError ? <div className="card">{detailError}</div> : null}
            {!detailError && detailLoading ? <div className="card">Loading vehicle details...</div> : null}

            {!detailLoading && !detailError && selectedVehicle ? (
              <div className="inventory-modal-body">
                <section className="inventory-modal-main">
                  <div className="inventory-modal-image">
                      {selectedVehiclePrimaryImage ? (
                        <img
                          src={selectedVehiclePrimaryImage}
                          alt={`${selectedVehicle.year} ${selectedVehicle.make} ${selectedVehicle.model}`}
                        />
                      ) : (
                      <img
                        src={FALLBACK_IMAGE}
                        alt={`${selectedVehicle.year} ${selectedVehicle.make} ${selectedVehicle.model}`}
                      />
                      )}
                    </div>
                  {selectedVehicleImages.length > 1 ? (
                    <div className="inventory-thumbnails">
                      {selectedVehicleImages.map((image) => (
                        <button
                          key={image}
                          className={`inventory-thumb ${selectedVehiclePrimaryImage === image ? "active" : ""}`}
                          onClick={() => setSelectedImage(image)}
                        >
                          <img src={image} alt="Vehicle thumbnail" loading="lazy" />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </section>

                <section className="inventory-modal-info">
                  <h2 style={{ marginTop: 0, marginBottom: 8 }}>
                    {selectedVehicle.year} {selectedVehicle.make} {selectedVehicle.model}
                  </h2>
                  <p style={{ marginTop: 0 }}>
                    {selectedVehicle.trim || "Base"} | {selectedVehicle.body_type || "Unknown"} |{" "}
                    {selectedVehicle.drivetrain || "N/A"}
                  </p>
                  <p className="inventory-price">${selectedVehicle.price_asking.toLocaleString()}</p>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <span className="badge">VIN {selectedVehicle.vin}</span>
                    <span className="badge">Mileage {formatMiles(selectedVehicle.odometer)}</span>
                    <span className="badge">
                      {selectedVehicle.location_state || "NA"} {selectedVehicle.location_zip || ""}
                    </span>
                    <span className="badge">Source {selectedVehicle.source_type || "unknown"}</span>
                    <span className="badge">{displayModeLabel(selectedVehicle.display_mode)}</span>
                    <span className="badge">{inspectionStatusLabel(selectedVehicle.inspection_status)}</span>
                  </div>

                  <div className="inventory-modal-specs">
                    <p>Engine: {selectedVehicle.engine_type || "N/A"}</p>
                    <p>Cylinders: {selectedVehicle.cylinders ?? "N/A"}</p>
                    <p>Condition: {selectedVehicle.condition_grade || "N/A"}</p>
                    <p>MPG: {selectedVehicle.mpg_combined ?? "N/A"}</p>
                    <p>Wholesale Estimate: {formatMoney(selectedVehicle.price_wholesale_est)}</p>
                    <p>Last Updated: {formatDate(selectedVehicle.updated_at)}</p>
                  </div>

                  {selectedVehicle.features_raw.length ? (
                    <div className="inventory-feature-grid">
                      {selectedVehicle.features_raw.slice(0, 20).map((feature) => (
                        <span className="badge" key={feature}>
                          {feature}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {selectedVehicle.display_context?.disclaimer ? (
                    <p style={{ marginBottom: 0 }}>{selectedVehicle.display_context.disclaimer}</p>
                  ) : null}

                  <div className="inventory-actions">
                    <button
                      className="button"
                      onClick={() => addToGarage(selectedVehicle.vin)}
                      disabled={garageVins.has(selectedVehicle.vin) || garageActionVin === selectedVehicle.vin}
                    >
                      {garageActionVin === selectedVehicle.vin
                        ? "Saving..."
                        : garageVins.has(selectedVehicle.vin)
                          ? "In Garage"
                          : "Add to My Garage"}
                    </button>
                    <button
                      className="button ghost"
                      onClick={() => startAcquisition(selectedVehicle.vin)}
                      disabled={garageActionVin === selectedVehicle.vin}
                    >
                      {garageActionVin === selectedVehicle.vin ? "Starting..." : "Start Acquisition"}
                    </button>
                    <Link className="button ghost" href={`/vinventory/${encodeURIComponent(selectedVehicle.vin)}` as any}>
                      Full Detail Page
                    </Link>
                    {selectedVehicle.source_url ? (
                      <a className="button ghost" href={selectedVehicle.source_url} target="_blank" rel="noreferrer">
                        Open Source Listing
                      </a>
                    ) : null}
                  </div>
                </section>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
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

function garageItemTitle(item: GarageItem): string {
  const year = item.vehicle.year ?? "";
  const make = item.vehicle.make ?? "";
  const model = item.vehicle.model ?? "";
  const title = `${year} ${make} ${model}`.trim();
  return title || item.vin;
}

function garageItemLocation(item: GarageItem): string {
  return `${item.vehicle.location_state || "NA"} ${item.vehicle.location_zip || ""}`.trim();
}

function formatMiles(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return value.toLocaleString();
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
