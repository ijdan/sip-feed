import { signOut } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function apiFetch(path: string, token: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (res.status === 401) {
    await signOut({ callbackUrl: "/" });
    throw new Error("Session expirée");
  }
  if (!res.ok) throw new Error(`API error ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

// Fetch public (sans token)
async function publicFetch(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export const api = {
  articles: {
    list: (token?: string, params?: Record<string, string>) => {
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return token
        ? apiFetch(`/articles/${qs}`, token)
        : publicFetch(`/articles/${qs}`);
    },
    get: (token: string, id: string) => apiFetch(`/articles/${id}`, token),
    stats: () => publicFetch("/articles/stats"),
  },
  sources: {
    list: (token: string) => apiFetch("/sources/", token),
    create: (token: string, body: object) =>
      apiFetch("/sources/", token, { method: "POST", body: JSON.stringify(body) }),
    update: (token: string, id: string, body: object) =>
      apiFetch(`/sources/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
    delete: (token: string, id: string) =>
      apiFetch(`/sources/${id}`, token, { method: "DELETE" }),
    toggle: (token: string, id: string) =>
      apiFetch(`/sources/${id}/toggle`, token, { method: "PATCH" }),
    collect: (token: string, id: string) =>
      apiFetch(`/admin/sources/${id}/collect`, token, { method: "POST" }),
  },
  users: {
    me: (token: string) => apiFetch("/users/me", token),
    updateMe: (token: string, body: object) =>
      apiFetch("/users/me", token, { method: "PATCH", body: JSON.stringify(body) }),
    deleteMe: (token: string) =>
      apiFetch("/users/me", token, { method: "DELETE" }),
    preferences: (token: string) => apiFetch("/users/me/preferences", token),
    updatePreferences: (token: string, body: object) =>
      apiFetch("/users/me/preferences", token, { method: "PUT", body: JSON.stringify(body) }),
    settings: (token: string) => apiFetch("/users/me/settings", token),
    updateSettings: (token: string, body: object) =>
      apiFetch("/users/me/settings", token, { method: "PUT", body: JSON.stringify(body) }),
  },
  admin: {
    settings: (token: string) => apiFetch("/admin/settings", token),
    updateSettings: (token: string, body: object) =>
      apiFetch("/admin/settings", token, { method: "PUT", body: JSON.stringify(body) }),
    report: (token: string) => apiFetch("/admin/report", token),
    syntheses: (token: string) => apiFetch("/admin/syntheses", token),
    generateSynthesis: (token: string) =>
      apiFetch("/admin/synthesis/generate", token, { method: "POST" }),
    stats: (token: string) => apiFetch("/admin/stats", token),
    logs: (token: string) => apiFetch("/admin/logs", token),
    collect: (token: string) =>
      apiFetch("/admin/collect", token, { method: "POST" }),
  },
};
