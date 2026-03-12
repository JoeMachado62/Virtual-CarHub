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

export default function AdminPage() {
  const [deals, setDeals] = useState<Deal[]>([]);

  async function loadDeals() {
    const response = await apiFetch<Deal[]>("/admin/deals", {}, undefined, true);
    if (response.status === "ok") setDeals(response.data || []);
  }

  useEffect(() => {
    void loadDeals();
  }, []);

  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">Internal</p>
        <h1>Admin workspace</h1>
      </section>
      <div className="card">
        <p>Service-token backed operations view (MVP internal console).</p>
        <button className="button" onClick={loadDeals}>
          Refresh Deals
        </button>
      </div>
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
