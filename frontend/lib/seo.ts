import type { Metadata } from "next";

import { maskVin } from "@/lib/vin";

const SITE_NAME = "VirtualCarHub";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://app.virtualcarhub.com";

/** Internal (server-side) API base for use in generateMetadata / sitemap / SSR fetches. */
export const API_INTERNAL =
  process.env.API_INTERNAL_BASE ||
  (process.env.NEXT_PUBLIC_API_BASE?.startsWith("http")
    ? process.env.NEXT_PUBLIC_API_BASE
    : "http://127.0.0.1:8000/v1");

export const SERVICE_TOKEN = process.env.NEXT_PUBLIC_SERVICE_TOKEN || "dev-service-token";

export async function fetchVehicleServer(vin: string) {
  try {
    const res = await fetch(`${API_INTERNAL}/inventory/${vin}`, {
      headers: { "X-Service-Token": SERVICE_TOKEN },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json.data ?? null;
  } catch {
    return null;
  }
}

/* ── Slug helpers ── */

export function slugify(value: string): string {
  return encodeURIComponent(value.trim());
}

export function deslugify(slug: string): string {
  return decodeURIComponent(slug).trim();
}

/* ── Canonical URL builders ── */

export function makeCanonical(make: string): string {
  return `${SITE_URL}/vinventory/make/${slugify(make)}`;
}

export function makeModelCanonical(make: string, model: string): string {
  return `${SITE_URL}/vinventory/make/${slugify(make)}/model/${slugify(model)}`;
}

export function makeModelTrimCanonical(make: string, model: string, trim: string): string {
  return `${SITE_URL}/vinventory/make/${slugify(make)}/model/${slugify(model)}/trim/${slugify(trim)}`;
}

export function vehicleCanonical(identifier: string, year: number, make: string, model: string): string {
  const slug = [make, model, String(year)]
    .map((p) => p.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""))
    .join("-");
  return `${SITE_URL}/cars/${identifier}/${slug}`;
}

/* ── Metadata builders ── */

export function makePageMetadata(make: string): Metadata {
  const title = `${make} Vehicles for Sale`;
  const description = `Find ${make} cars, trucks, and SUVs that ${SITE_NAME} can help you acquire through wholesale channels.`;
  const canonical = makeCanonical(make);
  return {
    title,
    description,
    keywords: `${make} for sale, buy ${make}, ${make} inventory, wholesale ${make}, ${make} cars`,
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: { title: `${title} | ${SITE_NAME}`, description, url: canonical, siteName: SITE_NAME },
  };
}

export function makeModelPageMetadata(make: string, model: string): Metadata {
  const title = `${make} ${model} for Sale`;
  const description = `Review ${make} ${model} opportunities that ${SITE_NAME} can help source, inspect, and acquire through wholesale channels.`;
  const canonical = makeModelCanonical(make, model);
  return {
    title,
    description,
    keywords: `${make} ${model} for sale, buy ${make} ${model}, ${make} ${model} price, ${make} ${model} inventory`,
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: { title: `${title} | ${SITE_NAME}`, description, url: canonical, siteName: SITE_NAME },
  };
}

export function makeModelTrimPageMetadata(make: string, model: string, trim: string): Metadata {
  const title = `${make} ${model} ${trim} for Sale`;
  const description = `View ${make} ${model} ${trim} vehicles available at ${SITE_NAME}. Compare pricing, photos, and specs for the ${make} ${model} ${trim}.`;
  const canonical = makeModelTrimCanonical(make, model, trim);
  return {
    title,
    description,
    keywords: `${make} ${model} ${trim} for sale, ${make} ${model} ${trim} price, buy ${make} ${model} ${trim}`,
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: { title: `${title} | ${SITE_NAME}`, description, url: canonical, siteName: SITE_NAME },
  };
}

export function vehiclePageMetadata(v: {
  vin: string;
  public_slug?: string | null;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
}): Metadata {
  const trimLabel = v.trim ? ` ${v.trim}` : "";
  const title = `${v.year} ${v.make} ${v.model}${trimLabel} for Sale`;
  const publicVin = maskVin(v.vin);
  const description = `View details, photos, and pricing for this ${v.year} ${v.make} ${v.model}${trimLabel}. VIN: ${publicVin}. Available at ${SITE_NAME}.`;
  const canonical = vehicleCanonical(v.public_slug || v.vin, v.year, v.make, v.model);
  return {
    title,
    description,
    keywords: `${v.year} ${v.make} ${v.model}${trimLabel}, ${v.make} ${v.model} for sale, VIN ${publicVin}`,
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: { title: `${title} | ${SITE_NAME}`, description, url: canonical, siteName: SITE_NAME },
  };
}

/* ── JSON-LD structured data builders ── */

export function autoDealerJsonLd(overrides?: Record<string, unknown>): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "AutoDealer",
    name: SITE_NAME,
    url: SITE_URL,
    description:
      "Buyer-side wholesale vehicle acquisition service helping consumers access dealer-only channels without traditional retail overhead.",
    ...overrides,
  };
}

export function vehicleOfferJsonLd(opts: { make: string; model?: string; trim?: string }): Record<string, unknown> {
  const item: Record<string, unknown> = {
    "@type": "Vehicle",
    manufacturer: { "@type": "Organization", name: opts.make },
  };
  if (opts.model) item.model = opts.model;
  if (opts.trim) item.vehicleConfiguration = opts.trim;

  return autoDealerJsonLd({
    makesOffer: {
      "@type": "Offer",
      itemOffered: item,
    },
  });
}

export function vehicleDetailJsonLd(v: {
  vin: string;
  year: number;
  make: string;
  model: string;
  trim?: string | null;
  price_asking?: number | null;
  odometer?: number | null;
  body_type?: string | null;
  drivetrain?: string | null;
  hero_image?: string | null;
}): Record<string, unknown> {
  const trimLabel = v.trim ? ` ${v.trim}` : "";
  const vehicle: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Vehicle",
    name: `${v.year} ${v.make} ${v.model}${trimLabel}`,
    manufacturer: { "@type": "Organization", name: v.make },
    model: v.model,
    vehicleIdentificationNumber: maskVin(v.vin),
    modelDate: String(v.year),
  };
  if (v.trim) vehicle.vehicleConfiguration = v.trim;
  if (v.body_type) vehicle.bodyType = v.body_type;
  if (v.drivetrain) vehicle.driveWheelConfiguration = v.drivetrain;
  if (v.odometer) {
    vehicle.mileageFromOdometer = {
      "@type": "QuantitativeValue",
      value: v.odometer,
      unitCode: "SMI",
    };
  }
  if (v.hero_image) vehicle.image = v.hero_image;
  if (v.price_asking) {
    vehicle.offers = {
      "@type": "Offer",
      price: v.price_asking,
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      seller: autoDealerJsonLd(),
    };
  }
  return vehicle;
}
