export type AuthState = {
  userId: string;
  email: string;
  accessToken: string;
  refreshToken: string;
};

const AUTH_STORAGE_KEY = "vch:auth:session";

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
