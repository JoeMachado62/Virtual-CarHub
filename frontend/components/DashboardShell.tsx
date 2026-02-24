"use client";

import { useEffect, useMemo, useState } from "react";

import { DannyChat } from "@/components/DannyChat";
import { DealTracker } from "@/components/DealTracker";
import { QuickMatchForm } from "@/components/QuickMatchForm";
import { Recommendation, RecommendationCards } from "@/components/RecommendationCards";
import { apiFetch } from "@/lib/api";
import { AuthState, clearAuthState, loadAuthState, saveAuthState } from "@/lib/auth";

export function DashboardShell() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [dealStage, setDealStage] = useState("LEAD");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [notifications, setNotifications] = useState<{ id: string; message: string }[]>([]);
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

    const [deal, recs, notes] = await Promise.all([
      apiFetch<{ stage: string }>("/me/deal", {}, auth.accessToken),
      apiFetch<Recommendation[]>("/me/recommendations", {}, auth.accessToken),
      apiFetch<{ id: string; message: string }[]>("/me/notifications", {}, auth.accessToken)
    ]);

    if (deal.status === "ok") setDealStage(deal.data.stage);
    if (recs.status === "ok") setRecommendations(recs.data || []);
    if (notes.status === "ok") setNotifications(notes.data || []);
  }

  useEffect(() => {
    void refreshData();
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
