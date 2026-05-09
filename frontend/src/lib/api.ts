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
  if (!res.ok) throw new Error(`API error ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  articles: {
    list: (token: string, params?: Record<string, string>) => {
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return apiFetch(`/articles/${qs}`, token);
    },
    get: (token: string, id: string) => apiFetch(`/articles/${id}`, token),
  },
  sources: {
    list: (token: string) => apiFetch("/sources/", token),
    create: (token: string, body: object) =>
      apiFetch("/sources/", token, { method: "POST", body: JSON.stringify(body) }),
    update: (token: string, id: string, body: object) =>
      apiFetch(`/sources/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
    delete: (token: string, id: string) =>
      apiFetch(`/sources/${id}`, token, { method: "DELETE" }),
  },
};
