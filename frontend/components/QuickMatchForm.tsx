"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/lib/api";

export function QuickMatchForm({
  accessToken,
  onCompleted,
  initialProfile
}: {
  accessToken: string;
  onCompleted: () => Promise<void>;
  initialProfile?: Record<string, unknown>;
}) {
  const p = initialProfile ?? {};
  const join = (v: unknown) =>
    Array.isArray(v) ? v.join(", ") : typeof v === "string" ? v : "";

  const [bodyTypes, setBodyTypes] = useState(join(p.body_types_included));
  const [budgetMin, setBudgetMin] = useState(Number(p.budget_min) || 0);
  const [budgetMax, setBudgetMax] = useState(Number(p.budget_max) || 0);
  const [yearMin, setYearMin] = useState(Number(p.year_min) || 0);
  const [yearMax, setYearMax] = useState(Number(p.year_max) || 0);
  const [mileageMin, setMileageMin] = useState(Number(p.mileage_min) || 0);
  const [mileageMax, setMileageMax] = useState(Number(p.mileage_max) || 0);
  const [priorities, setPriorities] = useState(join(p.top_3_priorities));
  const [brandsIn, setBrandsIn] = useState(join(p.brands_included));
  const [brandsEx, setBrandsEx] = useState(join(p.brands_excluded));
  const [deliveryZip, setDeliveryZip] = useState(
    typeof p.delivery_zip === "string" ? p.delivery_zip : ""
  );
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
          year_min: yearMin || null,
          year_max: yearMax || null,
          mileage_min: mileageMin || null,
          mileage_max: mileageMax || null,
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
            value={budgetMin || ""}
            placeholder="e.g. 20000"
            onChange={(e) => setBudgetMin(Number(e.target.value))}
          />
        </label>
        <label>
          Budget Max
          <input
            className="input"
            type="number"
            value={budgetMax || ""}
            placeholder="e.g. 45000"
            onChange={(e) => setBudgetMax(Number(e.target.value))}
          />
        </label>
      </div>
      <div className="grid two">
        <label>
          Year Min
          <input
            className="input"
            type="number"
            value={yearMin || ""}
            placeholder="e.g. 2018"
            onChange={(e) => setYearMin(Number(e.target.value))}
          />
        </label>
        <label>
          Year Max
          <input
            className="input"
            type="number"
            value={yearMax || ""}
            placeholder="e.g. 2025"
            onChange={(e) => setYearMax(Number(e.target.value))}
          />
        </label>
      </div>
      <div className="grid two">
        <label>
          Mileage Min
          <input
            className="input"
            type="number"
            value={mileageMin || ""}
            placeholder="e.g. 0"
            onChange={(e) => setMileageMin(Number(e.target.value))}
          />
        </label>
        <label>
          Mileage Max
          <input
            className="input"
            type="number"
            value={mileageMax || ""}
            placeholder="e.g. 60000"
            onChange={(e) => setMileageMax(Number(e.target.value))}
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
