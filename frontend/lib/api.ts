function resolveApiBase() {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  if (typeof window !== "undefined") return "/v1";
  return "http://127.0.0.1:8000/v1";
}

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
  const API_BASE = resolveApiBase();
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
