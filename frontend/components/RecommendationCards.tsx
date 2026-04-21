"use client";

import { maskVin } from "@/lib/vin";

export type Recommendation = {
  vin: string;
  match_score: number;
  explainability: string;
  market_retail: number;
  target_acquisition: number;
  estimated_otd: number;
  danny_savings: number;
  vehicle: {
    year: number;
    make: string;
    model: string;
    trim?: string;
    odometer?: number;
    price: number;
    location?: string;
  };
};

export function RecommendationCards({
  data,
  onSelect,
  onFavorite,
  isAdmin = false
}: {
  data: Recommendation[];
  onSelect: (vin: string) => Promise<void>;
  onFavorite: (vin: string) => Promise<void>;
  isAdmin?: boolean;
}) {
  if (!data.length) {
    return <div className="card">No recommendations yet. Complete Quick Match first.</div>;
  }

  return (
    <div className="grid two">
      {data.map((item) => (
        <article className="card" key={item.vin}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
            <strong>
              {item.vehicle.year} {item.vehicle.make} {item.vehicle.model}
            </strong>
            <span className="badge">Score {(item.match_score * 100).toFixed(0)}%</span>
          </div>
          <p style={{ marginBottom: 8 }}>{item.explainability}</p>
          <p>
            Price ${item.vehicle.price?.toLocaleString()} | OTD ${item.estimated_otd?.toLocaleString()} | Danny
            Savings ${item.danny_savings?.toLocaleString()}
          </p>
          <p>VIN: {maskVin(item.vin, isAdmin)}</p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="button" onClick={() => onSelect(item.vin)}>
              Select Vehicle
            </button>
            <button className="button ghost" onClick={() => onFavorite(item.vin)}>
              Favorite
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
