import { apiFetch } from "@/lib/api";

export type AuthState = {
  userId: string;
  email: string;
  accessToken: string;
  refreshToken: string;
};

const AUTH_STORAGE_KEY = "vch:auth:session";

type TokenPayload = {
  exp?: number;
};

function decodeJwtPayload(token: string): TokenPayload | null {
  if (typeof window === "undefined") return null;

  const [, payload] = token.split(".");
  if (!payload) return null;

  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = window.atob(padded);
    return JSON.parse(decoded) as TokenPayload;
  } catch {
    return null;
  }
}

export function loadAuthState(): AuthState | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AuthState>;
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.userId) return null;
    return {
      userId: parsed.userId,
      email: parsed.email || "",
      accessToken: parsed.accessToken,
      refreshToken: parsed.refreshToken,
    };
  } catch {
    return null;
  }
}

export function saveAuthState(auth: AuthState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
}

export function clearAuthState(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

export function isTokenExpired(token: string, skewSeconds = 30): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return true;
  const now = Math.floor(Date.now() / 1000);
  return payload.exp <= now + skewSeconds;
}

export async function refreshAuthState(auth: AuthState): Promise<AuthState | null> {
  if (typeof window === "undefined") return auth;

  if (isTokenExpired(auth.refreshToken, 30)) {
    clearAuthState();
    return null;
  }

  const response = await apiFetch<{
    access_token: string;
    refresh_token: string;
    token_type: string;
  }>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: auth.refreshToken })
  });

  if (response.status !== "ok" || !response.data?.access_token || !response.data?.refresh_token) {
    clearAuthState();
    return null;
  }

  const nextAuth: AuthState = {
    ...auth,
    accessToken: response.data.access_token,
    refreshToken: response.data.refresh_token
  };
  saveAuthState(nextAuth);
  return nextAuth;
}

export async function loadValidAuthState(): Promise<AuthState | null> {
  const auth = loadAuthState();
  if (!auth) return null;

  if (isTokenExpired(auth.refreshToken, 30)) {
    clearAuthState();
    return null;
  }

  if (!isTokenExpired(auth.accessToken, 60)) {
    return auth;
  }

  return refreshAuthState(auth);
}
