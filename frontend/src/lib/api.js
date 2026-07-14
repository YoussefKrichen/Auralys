import { STORAGE_KEYS } from "./storageKeys";

const DEV_PROXY_BASE = "/api";

function getDefaultApiBase() {
  const configuredBase = import.meta.env.VITE_API_BASE_URL;
  if (configuredBase) {
    return configuredBase;
  }
  if (import.meta.env.DEV) {
    return DEV_PROXY_BASE;
  }
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8000`;
}

export function getApiBase() {
  return localStorage.getItem(STORAGE_KEYS.apiBase) || getDefaultApiBase();
}

export function setApiBase(nextBase) {
  const normalizedBase = (nextBase || "").trim().replace(/\/+$/, "");
  if (!normalizedBase) {
    localStorage.removeItem(STORAGE_KEYS.apiBase);
    return getDefaultApiBase();
  }
  localStorage.setItem(STORAGE_KEYS.apiBase, normalizedBase);
  return normalizedBase;
}

export function buildApiUrl(path, base = getApiBase()) {
  return `${base.replace(/\/+$/, "")}${path}`;
}

function getAuthHeaders() {
  try {
    const session = JSON.parse(localStorage.getItem(STORAGE_KEYS.session) || "null");
    return session?.token ? { Authorization: `Bearer ${session.token}` } : {};
  } catch {
    return {};
  }
}

export async function fetchJson(path, init = {}, base) {
  const response = await fetch(buildApiUrl(path, base), {
    ...init,
    headers: { ...getAuthHeaders(), ...(init.headers || {}) },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      // Keep the HTTP fallback if the error payload is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

export function postJson(path, body, init = {}, base) {
  return fetchJson(
    path,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
      ...init,
      body: JSON.stringify(body),
    },
    base,
  );
}
