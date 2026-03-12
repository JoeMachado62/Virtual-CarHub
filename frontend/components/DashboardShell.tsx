"use client";

import { useEffect, useMemo, useState } from "react";

import { DannyChat } from "@/components/DannyChat";
import { DealTracker } from "@/components/DealTracker";
import { QuickMatchForm } from "@/components/QuickMatchForm";
import { Recommendation, RecommendationCards } from "@/components/RecommendationCards";
import { apiFetch } from "@/lib/api";
import { AuthState, clearAuthState, loadAuthState, saveAuthState } from "@/lib/auth";

type GarageItem = {
  id: string;
  vin: string;
  status: string;
  deal_stage: string;
  inspection_status: string;
  has_inspection_report: boolean;
  vehicle: {
    year?: number | null;
    make?: string | null;
    model?: string | null;
    trim?: string | null;
    price_asking?: number | null;
    location_state?: string | null;
    location_zip?: string | null;
    source_type?: string | null;
  };
};

export function DashboardShell() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [dealStage, setDealStage] = useState("LEAD");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [notifications, setNotifications] = useState<{ id: string; message: string }[]>([]);
  const [garageItems, setGarageItems] = useState<GarageItem[]>([]);
  const [garageMessage, setGarageMessage] = useState<string | null>(null);
  const [garageError, setGarageError] = useState<string | null>(null);
  const [garageActionVin, setGarageActionVin] = useState<string | null>(null);
  const [email, setEmail] = useState("buyer@example.com");
  const [password, setPassword] = useState("BuyerPass123!");
  const [loading, setLoading] = useState(false);

  const isAuthenticated = useMemo(() => Boolean(auth?.accessToken), [auth]);

  useEffect(() => {
    const saved = loadAuthState();
    if (saved) {
      setAuth(saved);
      if (saved.email) setEmail(saved.email);
    }
  }, []);

  async function login() {
    setLoading(true);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password })
      }
    );

    if (response.status === "ok") {
      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token
      };
      setAuth(nextAuth);
      saveAuthState(nextAuth);
    }
    setLoading(false);
  }

  async function refreshData() {
    if (!auth?.accessToken) return;

    const [deal, recs, notes, garage] = await Promise.all([
      apiFetch<{ stage: string }>("/me/deal", {}, auth.accessToken),
      apiFetch<Recommendation[]>("/me/recommendations", {}, auth.accessToken),
      apiFetch<{ id: string; message: string }[]>("/me/notifications", {}, auth.accessToken),
      apiFetch<GarageItem[]>("/me/garage", {}, auth.accessToken)
    ]);

    if (deal.status === "ok") setDealStage(deal.data.stage);
    if (recs.status === "ok") setRecommendations(recs.data || []);
    if (notes.status === "ok") setNotifications(notes.data || []);
    if (garage.status === "ok") setGarageItems(garage.data || []);
  }

  useEffect(() => {
    // Refresh dashboard state when the authenticated session changes.
    void refreshData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.accessToken]);

  async function selectVehicle(vin: string) {
    if (!auth?.accessToken) return;
    await apiFetch(`/me/recommendations/${vin}/select`, { method: "POST" }, auth.accessToken);
    await refreshData();
  }

  async function favoriteVehicle(vin: string) {
    if (!auth?.accessToken) return;
    await apiFetch(`/me/recommendations/${vin}/favorite`, { method: "POST" }, auth.accessToken);
    await refreshData();
  }

  async function initiateReturn() {
    if (!auth?.accessToken) return;
    await apiFetch(
      "/me/return/initiate",
      {
        method: "POST",
        body: JSON.stringify({ reason: "Preference changed", buyer_transport_responsibility: true })
      },
      auth.accessToken
    );
    await refreshData();
  }

  async function requestConditionReport(vin: string) {
    if (!auth?.accessToken) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch<{ message?: string; already_available?: boolean }>(
      `/me/vehicles/${vin}/condition-report-request`,
      { method: "POST" },
      auth.accessToken
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to request condition report.");
      setGarageActionVin(null);
      return;
    }
    setGarageMessage(
      response.data.message ||
        (response.data.already_available
          ? "Condition report is already available."
          : "Condition report requested. The auction queue has been updated.")
    );
    await refreshData();
    setGarageActionVin(null);
  }

  async function startGarageAcquisition(vin: string) {
    if (!auth?.accessToken) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch(`/me/garage/${vin}/acquire`, { method: "POST" }, auth.accessToken);
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to start acquisition.");
      setGarageActionVin(null);
      return;
    }
    setGarageMessage("Acquisition started. Returning the latest garage state.");
    await refreshData();
    setGarageActionVin(null);
  }

  if (!isAuthenticated) {
    return (
      <div className="card" style={{ maxWidth: 480, margin: "2rem auto" }}>
        <h2>Client Dashboard Login</h2>
        <p>Use seeded credentials for local MVP walkthrough.</p>
        <label>
          Email
          <input className="input" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="button" disabled={loading} onClick={login}>
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </div>
    );
  }

  const accessToken = auth?.accessToken ?? "";

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2>Deal Lifecycle Tracker</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="button ghost" onClick={refreshData}>
              Refresh
            </button>
            <button
              className="button ghost"
              onClick={() => {
                clearAuthState();
                setAuth(null);
              }}
            >
              Sign Out
            </button>
          </div>
        </div>
        <DealTracker stage={dealStage} />
      </section>

      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0 }}>My Garage</h2>
          <span className="badge">{garageItems.length} saved</span>
        </div>
        {garageError ? <p style={{ color: "#b42318", margin: 0 }}>{garageError}</p> : null}
        {garageMessage ? <p style={{ color: "#027a48", margin: 0 }}>{garageMessage}</p> : null}
        {!garageItems.length ? (
          <p style={{ marginBottom: 0 }}>Saved auction and inventory vehicles will appear here.</p>
        ) : (
          <div className="inventory-garage-grid">
            {garageItems.map((item) => (
              <article key={item.id} className="inventory-garage-item">
                <div>
                  <strong>{garageTitle(item)}</strong>
                  <p style={{ margin: 0 }}>
                    {formatMoney(item.vehicle.price_asking)} | {garageLocation(item)}
                  </p>
                  <p style={{ margin: 0 }}>VIN: {item.vin}</p>
                  <p style={{ margin: 0 }}>Status: {item.status}</p>
                  <p style={{ margin: 0 }}>Inspection: {item.inspection_status}</p>
                </div>
                <div className="inventory-actions">
                  <a className="button ghost" href={`/vinventory/${encodeURIComponent(item.vin)}`}>
                    Open
                  </a>
                  {(item.vehicle.source_type === "ove" || item.vehicle.source_type === "auction") && !item.has_inspection_report ? (
                    <button
                      className="button ghost"
                      onClick={() => requestConditionReport(item.vin)}
                      disabled={garageActionVin === item.vin}
                    >
                      {garageActionVin === item.vin ? "Requesting..." : "Condition Report"}
                    </button>
                  ) : null}
                  <button className="button" onClick={() => startGarageAcquisition(item.vin)} disabled={garageActionVin === item.vin}>
                    {garageActionVin === item.vin ? "Starting..." : "Start Acquisition"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <QuickMatchForm accessToken={accessToken} onCompleted={refreshData} />

      <section>
        <h2>Top Recommendations</h2>
        <RecommendationCards data={recommendations} onSelect={selectVehicle} onFavorite={favoriteVehicle} />
      </section>

      <section className="grid two">
        <DannyChat accessToken={accessToken} />

        <div className="card">
          <h3>Notifications</h3>
          {notifications.length ? (
            notifications.map((n) => <p key={n.id}>{n.message}</p>)
          ) : (
            <p>No notifications yet.</p>
          )}
          <button className="button" onClick={initiateReturn}>
            Initiate 7-Day Return
          </button>
        </div>
      </section>
    </div>
  );
}

function garageTitle(item: GarageItem): string {
  const title = `${item.vehicle.year || ""} ${item.vehicle.make || ""} ${item.vehicle.model || ""}`.trim();
  return title || item.vin;
}

function garageLocation(item: GarageItem): string {
  return `${item.vehicle.location_state || "NA"} ${item.vehicle.location_zip || ""}`.trim();
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toLocaleString()}`;
}
