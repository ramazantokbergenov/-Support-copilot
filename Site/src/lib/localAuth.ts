import { getApiBaseUrl } from "./supabase";

const LOCAL_TOKEN_KEY = "support-copilot.local-access-token";

export const localAuthEnabled = Boolean(import.meta.env.VITE_API_BASE_URL?.trim());

export function getLocalAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(LOCAL_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function clearLocalAccessToken() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(LOCAL_TOKEN_KEY);
  } catch {
    // Storage can be disabled by browser policy.
  }
}

export async function signInLocal(username: string, password: string): Promise<string> {
  const base = getApiBaseUrl();
  if (!base) throw new Error("Backend не настроен.");

  let response: Response;
  try {
    response = await fetch(`${base}/auth/token`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new Error("Не удалось связаться с Backend.");
  }

  const payload = await response.json().catch(() => null) as {
    access_token?: unknown;
    error?: { message?: string };
  } | null;
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? "Не удалось выполнить вход.");
  }
  if (typeof payload?.access_token !== "string") {
    throw new Error("Backend вернул некорректный токен.");
  }

  try {
    window.sessionStorage.setItem(LOCAL_TOKEN_KEY, payload.access_token);
  } catch {
    throw new Error("Браузер не разрешил сохранить сессию оператора.");
  }
  return payload.access_token;
}