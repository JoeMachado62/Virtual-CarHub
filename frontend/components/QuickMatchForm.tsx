"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/lib/api";

export function QuickMatchForm({
  accessToken,
  onCompleted
}: {
  accessToken: string;
  onCompleted: () => Promise<void>;
}) {
  const [bodyTypes, setBodyTypes] = useState("SUV,Sedan");
  const [budgetMin, setBudgetMin] = useState(20000);
  const [budgetMax, setBudgetMax] = useState(45000);
  const [priorities, setPriorities] = useState("safety,tech,fuel economy");
  const [brandsIn, setBrandsIn] = useState("Ford,Tesla");
  const [brandsEx, setBrandsEx] = useState("Mitsubishi");
  const [deliveryZip, setDeliveryZip] = useState("33445");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);

    await apiFetch(
      "/me/profile/quick-match",
      {
        method: "POST",
        body: JSON.stringify({
          body_types_included: bodyTypes.split(",").map((x) => x.trim()),
          budget_min: budgetMin,
          budget_max: budgetMax,
          top_3_priorities: priorities.split(",").map((x) => x.trim()).slice(0, 3),
          brands_included: brandsIn
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          brands_excluded: brandsEx
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          delivery_zip: deliveryZip
        })
      },
      accessToken
    );

    await onCompleted();
    setLoading(false);
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h3>Quick Match (5-step MVP)</h3>
      <p className="badge">Average completion: 60 seconds</p>
      <label>
        Body Types
        <input className="input" value={bodyTypes} onChange={(e) => setBodyTypes(e.target.value)} />
      </label>
      <div className="grid two">
        <label>
          Budget Min
          <input
            className="input"
            type="number"
            value={budgetMin}
            onChange={(e) => setBudgetMin(Number(e.target.value))}
          />
        </label>
        <label>
          Budget Max
          <input
            className="input"
            type="number"
            value={budgetMax}
            onChange={(e) => setBudgetMax(Number(e.target.value))}
          />
        </label>
      </div>
      <label>
        Top 3 Priorities
        <input className="input" value={priorities} onChange={(e) => setPriorities(e.target.value)} />
      </label>
      <label>
        Preferred Brands
        <input className="input" value={brandsIn} onChange={(e) => setBrandsIn(e.target.value)} />
      </label>
      <label>
        Excluded Brands
        <input className="input" value={brandsEx} onChange={(e) => setBrandsEx(e.target.value)} />
      </label>
      <label>
        Delivery ZIP
        <input className="input" value={deliveryZip} onChange={(e) => setDeliveryZip(e.target.value)} />
      </label>
      <button className="button" disabled={loading} type="submit">
        {loading ? "Running match..." : "Run Quick Match"}
      </button>
    </form>
  );
}
