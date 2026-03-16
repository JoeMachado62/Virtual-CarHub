function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function sanitizeApiBase(configuredBase?: string): string {
  const value = configuredBase?.trim();
  if (!value) return "/v1";

  if (typeof window === "undefined") return value;

  try {
    const url = new URL(value, window.location.origin);
    if (isLocalHostname(url.hostname) && !isLocalHostname(window.location.hostname)) {
      return "/v1";
    }
    return url.origin === window.location.origin ? `${url.pathname}${url.search}`.replace(/\/$/, "") : url.toString().replace(/\/$/, "");
  } catch {
    return value.startsWith("/") ? value.replace(/\/$/, "") : "/v1";
  }
}

function resolveApiBase() {
  if (typeof window !== "undefined") {
    return sanitizeApiBase(process.env.NEXT_PUBLIC_API_BASE);
  }
  return process.env.NEXT_PUBLIC_API_BASE?.trim() || "http://127.0.0.1:8000/v1";
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

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      cache: "no-store"
    });

    let payload: Record<string, unknown> | null = null;
    try {
      payload = (await response.json()) as Record<string, unknown>;
    } catch {
      payload = null;
    }

    if (response.status >= 400) {
      return {
        status: "error",
        data: null as T,
        error: {
          code: `HTTP_${response.status}`,
          message:
            (typeof payload?.detail === "string" && payload.detail) ||
            (typeof payload?.error === "object" &&
            payload?.error &&
            typeof (payload.error as { message?: unknown }).message === "string"
              ? ((payload.error as { message?: string }).message as string)
              : "") ||
            response.statusText ||
            "Request failed"
        }
      };
    }

    if (
      payload &&
      payload.status === "error" &&
      (!payload.error || typeof (payload.error as { message?: unknown }).message !== "string")
    ) {
      return {
        status: "error",
        data: null as T,
        error: {
          code: "INVALID_RESPONSE",
          message: "Invalid server response."
        }
      };
    }

    return (payload || {
      status: "error",
      data: null as T,
      error: {
        code: "INVALID_RESPONSE",
        message: "Invalid server response."
      }
    }) as ApiEnvelope<T>;
  } catch {
    return {
      status: "error",
      data: null as T,
      error: {
        code: "NETWORK_ERROR",
        message: "Unable to reach the VirtualCarHub API."
      }
    };
  }
}
