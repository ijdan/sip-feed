"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL;

async function toggleSource(token: string, id: string) {
  const res = await fetch(`${API}/sources/${id}/toggle`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Toggle failed");
  return res.json();
}

export default function SourceManager({ token }: { token: string }) {
  const { data: sources, isLoading } = useSWR("sources", () => api.sources.list(token));
  const [form, setForm] = useState({ name: "", type: "web", url: "", gmail_sender: "" });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const payload =
      form.type === "web"
        ? { name: form.name, type: "web", url: form.url, active: true }
        : { name: form.name, type: "gmail", gmail_sender: form.gmail_sender, active: true };
    await api.sources.create(token, payload);
    setForm({ name: "", type: "web", url: "", gmail_sender: "" });
    mutate("sources");
    setSubmitting(false);
  };

  const handleToggle = async (id: string) => {
    await toggleSource(token, id);
    mutate("sources");
  };

  const handleDelete = async (id: string) => {
    await api.sources.delete(token, id);
    mutate("sources");
  };

  return (
    <div className="space-y-8">
      <form onSubmit={handleSubmit} className="bg-white border rounded-lg p-6 space-y-4">
        <h3 className="font-semibold text-lg">Ajouter une source</h3>
        <div className="grid grid-cols-2 gap-4">
          <input
            required
            placeholder="Nom de la source"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="border rounded px-3 py-2 text-sm col-span-2"
          />
          <select
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          >
            <option value="web">Site web</option>
            <option value="gmail">Newsletter Gmail</option>
          </select>
          {form.type === "web" ? (
            <input
              required
              placeholder="https://..."
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              className="border rounded px-3 py-2 text-sm"
            />
          ) : (
            <input
              required
              placeholder="expediteur@newsletter.com"
              value={form.gmail_sender}
              onChange={(e) => setForm({ ...form, gmail_sender: e.target.value })}
              className="border rounded px-3 py-2 text-sm"
            />
          )}
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Ajout..." : "Ajouter"}
        </button>
      </form>

      <div className="space-y-3">
        <h3 className="font-semibold text-lg">Sources configurées</h3>
        {isLoading && <p className="text-gray-500 text-sm">Chargement...</p>}
        {sources?.map((s: any) => (
          <div key={s.id} className={`bg-white border rounded-lg px-5 py-3 flex items-center justify-between gap-4 transition ${!s.active ? "opacity-50" : ""}`}>
            <div className="flex items-center gap-3 min-w-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${s.active ? "bg-green-500" : "bg-gray-300"}`} />
              <div className="min-w-0">
                <span className="font-medium text-sm">{s.name}</span>
                <span className="ml-2 text-xs text-gray-400 truncate">
                  {s.type === "web" ? s.url : s.gmail_sender}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => handleToggle(s.id)}
                className={`text-xs px-2 py-1 rounded border transition ${s.active ? "border-gray-300 text-gray-600 hover:border-gray-500" : "border-blue-300 text-blue-600 hover:border-blue-500"}`}
              >
                {s.active ? "Désactiver" : "Activer"}
              </button>
              <button
                onClick={() => handleDelete(s.id)}
                className="text-red-500 text-sm hover:underline"
              >
                Supprimer
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
