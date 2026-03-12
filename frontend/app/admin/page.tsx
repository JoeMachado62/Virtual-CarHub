"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

type Deal = {
  id: string;
  user_id: string;
  stage: string;
  funding_state: string;
  selected_vin?: string;
};

type PendingOveDetailRequest = {
  request_id: string;
  vin: string;
  source_platform: string;
  status: string;
  priority: number;
  attempts: number;
  requested_at?: string | null;
  last_polled_at?: string | null;
  request_source?: string | null;
  requested_by?: string | null;
  reason?: string | null;
  metadata?: Record<string, unknown> | null;
};

export default function AdminPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [pendingRequests, setPendingRequests] = useState<PendingOveDetailRequest[]>([]);

  async function loadDeals() {
    const response = await apiFetch<Deal[]>("/admin/deals", {}, undefined, true);
    if (response.status === "ok") setDeals(response.data || []);
  }

  async function loadPendingRequests() {
    const response = await apiFetch<{ items: PendingOveDetailRequest[] }>(
      "/inventory/ove/detail/pending?limit=100",
      {},
      undefined,
      true
    );
    if (response.status === "ok") setPendingRequests(response.data.items || []);
  }

  useEffect(() => {
    void loadDeals();
    void loadPendingRequests();
  }, []);

  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">Internal</p>
        <h1>Admin workspace</h1>
      </section>
      <div className="card">
        <p>Service-token backed operations view (MVP internal console).</p>
        <div className="inventory-actions">
          <button className="button" onClick={loadDeals}>
            Refresh Deals
          </button>
          <button className="button ghost" onClick={loadPendingRequests}>
            Refresh Auction Queue
          </button>
        </div>
      </div>
      <section className="section-shell">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <p className="section-eyebrow" style={{ marginBottom: 8 }}>Scraper Queue</p>
            <h2 style={{ margin: 0 }}>Pending auction detail requests</h2>
          </div>
          <span className="badge">{pendingRequests.length} pending</span>
        </div>
        {!pendingRequests.length ? (
          <div className="card">
            <p style={{ margin: 0 }}>No pending OVE detail requests right now.</p>
          </div>
        ) : (
          <div className="grid">
            {pendingRequests.map((item) => (
              <article className="card" key={item.request_id}>
                <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
                  <span className="badge">{item.source_platform}</span>
                  <span className="badge">Priority {item.priority}</span>
                  <span className="badge">Attempts {item.attempts}</span>
                  <span className="badge">{item.status}</span>
                </div>
                <p>
                  <strong>{item.vin}</strong>
                </p>
                <p>Requested by: {item.requested_by || "system"}</p>
                <p>Source: {item.request_source || "unknown"}</p>
                <p>Reason: {item.reason || "n/a"}</p>
                <p>Requested at: {formatDate(item.requested_at)}</p>
                <p>Last polled: {formatDate(item.last_polled_at)}</p>
                {item.metadata ? (
                  <div className="inventory-modal-specs">
                    <strong>Request metadata</strong>
                    <p style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(item.metadata, null, 2)}</p>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
      <div className="grid" style={{ marginTop: 12 }}>
        {deals.map((deal) => (
          <article className="card" key={deal.id}>
            <p>
              <strong>{deal.id}</strong>
            </p>
            <p>User: {deal.user_id}</p>
            <p>Stage: {deal.stage}</p>
            <p>Funding: {deal.funding_state}</p>
            <p>Selected VIN: {deal.selected_vin || "n/a"}</p>
          </article>
        ))}
      </div>
    </main>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}
