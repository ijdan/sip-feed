"use client";
import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

async function apiFetch(path: string, token: string, options: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers },
  });
  if (!res.ok) {
    let detail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch { /* corps non JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

interface SummaryPromptData {
  prompt: string;
  is_custom: boolean;
  default_prompt: string;
  prompt_version: string;
  updated_at: string | null;
  updated_by: string | null;
}

export default function SummaryPromptEditor({ token }: { token: string }) {
  const { data, isLoading } = useSWR<SummaryPromptData>(
    "admin-summary-prompt",
    () => apiFetch("/admin/summary-prompt", token)
  );

  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (data) setDraft(data.prompt);
  }, [data]);

  const dirty = data !== undefined && draft !== data.prompt;

  const save = async (prompt: string) => {
    setSaving(true);
    setMessage("");
    try {
      const updated = await apiFetch("/admin/summary-prompt", token, {
        method: "PUT",
        body: JSON.stringify({ prompt }),
      });
      mutate("admin-summary-prompt", updated, false);
      setDraft(updated.prompt);
      setMessage("✓ Prompt enregistré — les résumés en cache seront régénérés");
    } catch (e) {
      setMessage(`✗ ${e instanceof Error ? e.message : "Erreur"}`);
    } finally {
      setSaving(false);
      setTimeout(() => setMessage(""), 6000);
    }
  };

  const resetToDefault = async () => {
    if (!confirm("Réinitialiser le prompt à la version par défaut du code ?")) return;
    await save("");
  };

  if (isLoading || !data) return <p className="text-sm text-gray-400">Chargement du prompt...</p>;

  return (
    <div className="bg-white border rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-semibold text-lg">Prompt de génération LinkedIn</h3>
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium ${
            data.is_custom ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-500"
          }`}
        >
          {data.is_custom ? "Personnalisé" : "Par défaut"}
        </span>
      </div>

      <p className="text-xs text-gray-400">
        Utilisé par le bouton de résumé d&apos;article (post LinkedIn FR + EN). Placeholders disponibles :{" "}
        <code className="bg-gray-100 px-1 rounded">{"{title}"}</code>,{" "}
        <code className="bg-gray-100 px-1 rounded">{"{source}"}</code>,{" "}
        <code className="bg-gray-100 px-1 rounded">{"{text}"}</code> (obligatoire — texte de l&apos;article).
        La réponse doit rester un JSON avec <code className="bg-gray-100 px-1 rounded">summary_fr</code> et{" "}
        <code className="bg-gray-100 px-1 rounded">summary_en</code>. Toute modification invalide les résumés
        déjà en cache : ils seront régénérés à la prochaine consultation.
      </p>

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        disabled={saving}
        rows={18}
        spellCheck={false}
        className="w-full border rounded p-3 text-sm font-mono text-gray-800 leading-relaxed disabled:opacity-50"
      />

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => save(draft)}
          disabled={saving || !dirty || !draft.trim()}
          className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
          style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
        >
          {saving ? "Enregistrement…" : "Enregistrer le prompt"}
        </button>
        <button
          onClick={resetToDefault}
          disabled={saving || !data.is_custom}
          className="px-4 py-2 rounded text-sm font-medium border text-gray-600 hover:bg-gray-50 transition disabled:opacity-40"
        >
          Réinitialiser au défaut
        </button>
        {message && (
          <span
            className="text-sm font-medium"
            style={{ color: message.startsWith("✓") ? "#22c55e" : "#ef4444" }}
          >
            {message}
          </span>
        )}
      </div>

      {data.is_custom && data.updated_at && (
        <p className="text-xs text-gray-400">
          Dernière modification : {new Date(data.updated_at).toLocaleString("fr-FR")}
          {data.updated_by ? ` par ${data.updated_by}` : ""}
        </p>
      )}
    </div>
  );
}
