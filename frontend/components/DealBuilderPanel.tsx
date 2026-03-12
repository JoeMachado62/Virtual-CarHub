"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export function DealBuilderPanel() {
  const router = useRouter();
  const [query, setQuery] = useState("I want a 2021 BMW X5 with under 40k miles...");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    if (!nextQuery) {
      router.push("/vinventory");
      return;
    }
    router.push(`/vinventory?q=${encodeURIComponent(nextQuery)}`);
  }

  return (
    <aside className="deal-builder-card">
      <p className="section-eyebrow">Build Your Deal</p>
      <h2>Tell our AI exactly what you want.</h2>
      <p className="muted-copy">
        Describe the vehicle, price band, mileage, or equipment you want and jump straight into live wholesale search.
      </p>

      <form className="deal-builder-form" onSubmit={onSubmit}>
        <textarea
          rows={4}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="I want a 2021 BMW X5 with under 40k miles..."
        />
        <button type="submit" className="button">
          Browse Matches
        </button>
      </form>

      <div className="deal-builder-badges">
        <span className="badge">Powered by live auction + retail feeds</span>
        <span className="badge">Pre-approval friendly</span>
      </div>
    </aside>
  );
}
