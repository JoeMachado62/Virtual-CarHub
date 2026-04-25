"use client";

import { FormEvent, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api";
import { BODY_TYPE_OPTIONS, MAKE_OPTIONS } from "@/lib/vehicleOptions";

/* ── Accordion multi-select with badge count ── */

type AccordionId = "bodyTypes" | "brandsIn" | "brandsEx";

function MultiSelect({
  id,
  label,
  options,
  selected,
  onChange,
  openId,
  onToggleOpen,
}: {
  id: AccordionId;
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  openId: AccordionId | null;
  onToggleOpen: (id: AccordionId) => void;
}) {
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const isOpen = openId === id;

  function toggle(value: string) {
    const lower = value.toLowerCase();
    if (selectedSet.has(lower)) {
      onChange(selected.filter((s) => s !== lower));
    } else {
      onChange([...selected, lower]);
    }
  }

  return (
    <div className="qm-accordion">
      <button
        type="button"
        className="qm-accordion-header"
        onClick={() => onToggleOpen(id)}
        aria-expanded={isOpen}
      >
        <span className="qm-accordion-label">
          {label}
          {selected.length > 0 && (
            <span className="qm-accordion-badge">{selected.length}</span>
          )}
        </span>
        <span className={`qm-accordion-arrow${isOpen ? " open" : ""}`}>&#9662;</span>
      </button>
      {isOpen && (
        <div className="multi-select-list qm-multi-select">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              className={`multi-select-item${selectedSet.has(opt.toLowerCase()) ? " selected" : ""}`}
              onClick={() => toggle(opt)}
              title={opt}
            >
              <span>{opt}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── QuickMatchForm ── */

export function QuickMatchForm({
  accessToken,
  onCompleted,
  initialProfile,
}: {
  accessToken: string;
  onCompleted: () => Promise<void>;
  initialProfile?: Record<string, unknown>;
}) {
  const p = initialProfile ?? {};
  const toArr = (v: unknown): string[] =>
    Array.isArray(v) ? v.map((s) => String(s).toLowerCase()) : [];
  const [openAccordion, setOpenAccordion] = useState<AccordionId | null>(null);

  function toggleAccordion(id: AccordionId) {
    setOpenAccordion((prev) => (prev === id ? null : id));
  }

  const [bodyTypes, setBodyTypes] = useState<string[]>(toArr(p.body_types_included));
  const [budgetMin, setBudgetMin] = useState(Number(p.budget_min) || 0);
  const [budgetMax, setBudgetMax] = useState(Number(p.budget_max) || 0);
  const [yearMin, setYearMin] = useState(Number(p.year_min) || 0);
  const [yearMax, setYearMax] = useState(Number(p.year_max) || 0);
  const [mileageMin, setMileageMin] = useState(Number(p.mileage_min) || 0);
  const [mileageMax, setMileageMax] = useState(Number(p.mileage_max) || 0);
  const [priorities, setPriorities] = useState(
    Array.isArray(p.top_3_priorities) ? p.top_3_priorities.join(", ") : typeof p.top_3_priorities === "string" ? p.top_3_priorities : ""
  );
  const [brandsIn, setBrandsIn] = useState<string[]>(toArr(p.brands_included));
  const [brandsEx, setBrandsEx] = useState<string[]>(toArr(p.brands_excluded));
  const [deliveryZip, setDeliveryZip] = useState(
    typeof p.delivery_zip === "string" ? p.delivery_zip : ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const response = await apiFetch(
      "/me/profile/quick-match",
      {
        method: "POST",
        body: JSON.stringify({
          body_types_included: bodyTypes,
          budget_min: budgetMin,
          budget_max: budgetMax,
          year_min: yearMin || null,
          year_max: yearMax || null,
          mileage_min: mileageMin || null,
          mileage_max: mileageMax || null,
          top_3_priorities: priorities
            .split(",")
            .map((x) => x.trim())
            .slice(0, 3),
          brands_included: brandsIn,
          brands_excluded: brandsEx,
          delivery_zip: deliveryZip,
        }),
      },
      accessToken
    );

    if (response.status !== "ok") {
      setError(response.error?.message || "Danny could not save your Quick Match yet.");
      setLoading(false);
      return;
    }

    await onCompleted();
    setLoading(false);
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h3>Quick Match</h3>
      <p className="badge">Average completion: 60 seconds</p>

      <MultiSelect
        id="bodyTypes"
        label="Body Types"
        options={BODY_TYPE_OPTIONS}
        selected={bodyTypes}
        onChange={setBodyTypes}
        openId={openAccordion}
        onToggleOpen={toggleAccordion}
      />

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

      <MultiSelect
        id="brandsIn"
        label="Preferred Brands"
        options={MAKE_OPTIONS}
        selected={brandsIn}
        onChange={setBrandsIn}
        openId={openAccordion}
        onToggleOpen={toggleAccordion}
      />
      <MultiSelect
        id="brandsEx"
        label="Excluded Brands"
        options={MAKE_OPTIONS}
        selected={brandsEx}
        onChange={setBrandsEx}
        openId={openAccordion}
        onToggleOpen={toggleAccordion}
      />

      <label>
        Delivery ZIP
        <input className="input" value={deliveryZip} onChange={(e) => setDeliveryZip(e.target.value)} />
      </label>
      <button className="button" disabled={loading} type="submit">
        {loading ? "Running match..." : "Run Quick Match"}
      </button>
      {error ? <p className="dashboard-error">{error}</p> : null}
    </form>
  );
}
