const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/v1";
const SERVICE_TOKEN = process.env.NEXT_PUBLIC_SERVICE_TOKEN ?? "dev-service-token";

export type ApiEnvelope<T> = {
  status: "ok" | "error";
  data: T;
  error: { code: string; message: string } | null;
};

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
  service = false
): Promise<ApiEnvelope<T>> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (service) headers.set("X-Service-Token", SERVICE_TOKEN);

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store"
  });

  return response.json();
}
