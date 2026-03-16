"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { formatAuctionPlatformLabel } from "@/lib/sourceLabels";

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
  const [vin, setVin] = useState("");
  const [sourcePlatform, setSourcePlatform] = useState("manheim");
  const [priority, setPriority] = useState("10");
  const [reason, setReason] = useState("manual_pi_pull");
  const [requestedBy, setRequestedBy] = useState("admin_workspace");
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

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

  async function submitManualRequest(event: FormEvent) {
    event.preventDefault();
    const normalizedVin = vin.trim().toUpperCase();
    if (normalizedVin.length !== 17) {
      setQueueError("VIN must be 17 characters.");
      setQueueMessage(null);
      return;
    }

    setQueueLoading(true);
    setQueueError(null);
    setQueueMessage(null);
    const response = await apiFetch<{
      request_id: string;
      deduplicated?: boolean;
      status?: string;
    }>(
      `/inventory/ove/detail/${encodeURIComponent(normalizedVin)}/request`,
      {
        method: "POST",
        body: JSON.stringify({
          source_platform: sourcePlatform,
          priority: Number(priority) || 10,
          request_source: "pi_console",
          requested_by: requestedBy.trim() || "admin_workspace",
          reason: reason.trim() || "manual_pi_pull",
          metadata: {
            manual_request: true,
            console: "admin_workspace"
          }
        })
      },
      undefined,
      true
    );

    if (response.status !== "ok") {
      setQueueError(response.error?.message || "Unable to queue manual auction detail pull.");
      setQueueLoading(false);
      return;
    }

    setVin(normalizedVin);
    setQueueMessage(
      response.data.deduplicated
        ? `VIN ${normalizedVin} was already queued. Existing request ${response.data.request_id} remains active.`
        : `VIN ${normalizedVin} queued successfully as request ${response.data.request_id}.`
    );
    setQueueLoading(false);
    await loadPendingRequests();
  }

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
        <div>
          <p className="section-eyebrow" style={{ marginBottom: 8 }}>PI Workflow</p>
          <h2 style={{ margin: 0 }}>Pull a specific auction VIN now</h2>
        </div>
        <form className="inventory-filter-form" onSubmit={submitManualRequest}>
          <div className="inventory-mini-grid">
            <label>
              VIN
              <input
                className="input"
                maxLength={17}
                placeholder="1HGCM82633A123456"
                value={vin}
                onChange={(event) => setVin(event.target.value.toUpperCase())}
              />
            </label>
            <label>
              Auction Source
              <select className="select" value={sourcePlatform} onChange={(event) => setSourcePlatform(event.target.value)}>
                <option value="manheim">Primary Auction Feed</option>
                <option value="openlane">OPENLANE</option>
                <option value="ally-smart-auction">SmartAuction</option>
              </select>
            </label>
          </div>
          <div className="inventory-mini-grid">
            <label>
              Priority
              <input
                className="input"
                type="number"
                min="1"
                max="999"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              />
            </label>
            <label>
              Requested By
              <input
                className="input"
                value={requestedBy}
                onChange={(event) => setRequestedBy(event.target.value)}
              />
            </label>
          </div>
          <label>
            Reason
            <input className="input" value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          {queueError ? <p style={{ color: "#b42318", margin: 0 }}>{queueError}</p> : null}
          {queueMessage ? <p style={{ color: "#027a48", margin: 0 }}>{queueMessage}</p> : null}
          <div className="inventory-actions">
            <button className="button" type="submit" disabled={queueLoading}>
              {queueLoading ? "Queueing..." : "Queue VIN Pull"}
            </button>
            {vin.trim().length === 17 ? (
              <>
                <a className="button ghost" href={`/vinventory/${encodeURIComponent(vin.trim().toUpperCase())}`}>
                  Open Vehicle
                </a>
                <a
                  className="button ghost"
                  href={`/vinventory/${encodeURIComponent(vin.trim().toUpperCase())}/condition-report`}
                >
                  Open Report
                </a>
              </>
            ) : null}
          </div>
        </form>
      </section>
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
            <p style={{ margin: 0 }}>No pending auction detail requests right now.</p>
          </div>
        ) : (
          <div className="grid">
            {pendingRequests.map((item) => (
              <article className="card" key={item.request_id}>
                <div className="inventory-feature-grid" style={{ marginBottom: 12 }}>
                  <span className="badge">{formatAuctionPlatformLabel(item.source_platform)}</span>
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
                <div className="inventory-actions">
                  <a className="button ghost" href={`/vinventory/${encodeURIComponent(item.vin)}`}>
                    Open Vehicle
                  </a>
                  <a className="button ghost" href={`/vinventory/${encodeURIComponent(item.vin)}/condition-report`}>
                    Open Report
                  </a>
                </div>
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
