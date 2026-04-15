import { MetadataRoute } from "next";
import { API_INTERNAL, SERVICE_TOKEN } from "@/lib/seo";

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://app.virtualcarhub.com";

function enc(value: string): string {
  return encodeURIComponent(value.trim());
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: BASE_URL, changeFrequency: "daily", priority: 1.0 },
    { url: `${BASE_URL}/vinventory`, changeFrequency: "daily", priority: 0.9 },
    { url: `${BASE_URL}/about`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${BASE_URL}/financing`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${BASE_URL}/contact`, changeFrequency: "monthly", priority: 0.4 },
  ];

  try {
    const res = await fetch(`${API_INTERNAL}/inventory/taxonomy/list`, {
      headers: { "X-Service-Token": SERVICE_TOKEN },
      cache: "no-store",
    });
    if (!res.ok) return entries;
    const json = await res.json();
    const routes: { make: string; model: string; trim: string }[] = json.data?.routes ?? [];

    const makes = new Set<string>();
    const makeModels = new Set<string>();

    for (const route of routes) {
      const makeSlug = enc(route.make);

      if (!makes.has(route.make)) {
        makes.add(route.make);
        entries.push({
          url: `${BASE_URL}/vinventory/make/${makeSlug}`,
          changeFrequency: "weekly",
          priority: 0.8,
        });
      }

      const mmKey = `${route.make}|||${route.model}`;
      if (!makeModels.has(mmKey)) {
        makeModels.add(mmKey);
        entries.push({
          url: `${BASE_URL}/vinventory/make/${makeSlug}/model/${enc(route.model)}`,
          changeFrequency: "weekly",
          priority: 0.7,
        });
      }

      if (route.trim) {
        entries.push({
          url: `${BASE_URL}/vinventory/make/${makeSlug}/model/${enc(route.model)}/trim/${enc(route.trim)}`,
          changeFrequency: "monthly",
          priority: 0.6,
        });
      }
    }
  } catch {
    // If taxonomy API is unavailable, return static entries only
  }

  return entries;
}
