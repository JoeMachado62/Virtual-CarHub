"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

const SEARCH_CONTEXT_KEY = "vch:inventory:search-context";

type ParseQueryResponse = {
  filters: Record<string, string | number | boolean>;
  parsed: boolean;
  parse_method: string;
  raw_query: string;
};

export function DealBuilderPanel() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zipCode, setZipCode] = useState("");
  const [pendingFilters, setPendingFilters] = useState<Record<string, string | number | boolean> | null>(null);
  const [pendingRawQuery, setPendingRawQuery] = useState("");

  // Restore ZIP from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SEARCH_CONTEXT_KEY);
      if (raw) {
        const stored = JSON.parse(raw) as { zip_code?: string };
        if (stored.zip_code) setZipCode(stored.zip_code);
      }
    } catch { /* ignore */ }
  }, []);

  function navigateWithFilters(
    filters: Record<string, string | number | boolean>,
    rawQuery: string,
    zip: string,
  ) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== null && value !== undefined && value !== "") {
        params.set(key, String(value));
      }
    }
    if (zip && !params.has("zip_code")) {
      params.set("zip_code", zip);
    }
    params.set("nlp_query", rawQuery);

    // Persist ZIP for future searches
    if (zip) {
      try {
        window.localStorage.setItem(
          SEARCH_CONTEXT_KEY,
          JSON.stringify({ zip_code: zip }),
        );
      } catch { /* ignore */ }
    }

    router.push(`/vinventory?${params.toString()}`);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    setError(null);
    if (!nextQuery) {
      router.push("/vinventory");
      return;
    }

    setLoading(true);

    try {
      const response = await apiFetch<ParseQueryResponse>(
        "/inventory/parse-query",
        {
          method: "POST",
          body: JSON.stringify({ query: nextQuery }),
        },
      );

      if (response.status === "ok" && response.data.parsed) {
        const filters = response.data.filters;
        const hasZip = Boolean(
          filters.zip_code || zipCode,
        );
        const isAuction = filters.source_type === "auction";
        const isVinSearch = Boolean(filters.vin);

        // VIN searches don't need a ZIP — they find a specific vehicle
        if (!hasZip && !isAuction && !isVinSearch) {
          // Need ZIP — show prompt
          setPendingFilters(filters);
          setPendingRawQuery(nextQuery);
          setLoading(false);
          return;
        }

        navigateWithFilters(filters, nextQuery, zipCode);
      } else {
        setError(
          response.error?.message ||
            "Danny could not understand that request yet. Try adding a make, model, budget, mileage, or must-have feature.",
        );
      }
    } catch {
      setError(
        "Danny cannot reach the inventory AI right now. Check that the VirtualCarHub API is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  function onZipSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const zip = zipCode.trim();
    if (!zip || !/^\d{5}$/.test(zip)) return;

    if (pendingFilters) {
      navigateWithFilters(pendingFilters, pendingRawQuery, zip);
    } else {
      router.push(
        `/vinventory?q=${encodeURIComponent(pendingRawQuery)}&zip_code=${encodeURIComponent(zip)}`,
      );
    }
  }

  // ZIP code prompt step
  if (pendingFilters !== null) {
    return (
      <aside className="deal-builder-card">
        <p className="section-eyebrow">Build Your Deal</p>
        <h2>Almost there — where are you located?</h2>
        <p className="muted-copy">
          Enter your ZIP code so Danny can compare vehicles that make sense for your area.
        </p>
        <form className="deal-builder-form" onSubmit={onZipSubmit}>
          <input
            type="text"
            inputMode="numeric"
            pattern="\d{5}"
            maxLength={5}
            value={zipCode}
            onChange={(event) => setZipCode(event.target.value.replace(/\D/g, ""))}
            placeholder="Enter your ZIP code"
            autoFocus
            style={{
              padding: "0.75rem 1rem",
              fontSize: "1rem",
              border: "1px solid var(--border)",
              borderRadius: "0.5rem",
              width: "100%",
            }}
          />
          <button
            type="submit"
            className="button"
            disabled={!/^\d{5}$/.test(zipCode.trim())}
          >
            Search Inventory
          </button>
          <button
            type="button"
            className="button"
            style={{
              background: "transparent",
              color: "var(--foreground)",
              border: "1px solid var(--border)",
            }}
            onClick={() => {
              setPendingFilters(null);
              setPendingRawQuery("");
              setError(null);
            }}
          >
            Back
          </button>
        </form>
      </aside>
    );
  }

  return (
    <aside className="deal-builder-card">
      <p className="section-eyebrow">Build Your Deal</p>
      <h2>Tell Danny exactly what you want.</h2>
      <p className="muted-copy">
        Describe the vehicle, price range, mileage, or features you want. Danny will turn it into a live wholesale
        search.
      </p>

      <form className="deal-builder-form" onSubmit={onSubmit}>
        <textarea
          rows={4}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="I want a 2021 BMW X5 with under 40k miles..."
          disabled={loading}
        />
        <button type="submit" className="button" disabled={loading}>
          {loading ? "Finding matches..." : "Browse Matches"}
        </button>
      </form>
      {error ? <p className="dashboard-error">{error}</p> : null}

      <div className="deal-builder-badges">
        <span className="badge">Wholesale + retail inventory</span>
        <span className="badge">Built around your budget</span>
      </div>
    </aside>
  );
}
