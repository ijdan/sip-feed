"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

const MODEL_LABELS: Record<string, { label: string; note?: string }> = {
  "gemini-3.5-flash":        { label: "Gemini 3.5 Flash",     note: "Dernière génération — GA" },
  "gemini-3.1-flash-lite":   { label: "Gemini 3.1 Flash Lite",note: "Rapide — stable" },
  "gemini-3-flash-preview":  { label: "Gemini 3 Flash",       note: "Preview — fallback" },
  "gemma-4-31b-it":          { label: "Gemma 4 31B",          note: "Open source — 31B" },
  "gemma-4-26b-a4b-it":      { label: "Gemma 4 26B",          note: "Dernier recours" },
};

async function apiFetch(path: string, token: string, options: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

const LOOKBACK_OPTIONS = [1, 2, 3, 5, 7, 10];
const RETENTION_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 7, 15, 30, 90, 365];

interface Settings {
  llm_enabled: boolean;
  thinking_enabled: boolean;
  model_priority: string[];
  gmail_lookback_days: number;
  retention_days: number;
  interest: string;
}

export default function AdminSettings({ token }: { token: string }) {
  const { data: settings, isLoading } = useSWR<Settings>(
    "admin-settings",
    () => apiFetch("/admin/settings", token)
  );

  const [saving, setSaving] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectMsg, setCollectMsg] = useState("");

  const launchCollect = async () => {
    setCollecting(true);
    setCollectMsg("");
    try {
      await apiFetch("/admin/collect", token, { method: "POST" });
      setCollectMsg("✓ Collecte lancée");
    } catch {
      setCollectMsg("✗ Erreur");
    } finally {
      setCollecting(false);
      setTimeout(() => setCollectMsg(""), 4000);
    }
  };

  const updateSettings = async (updated: Settings) => {
    setSaving(true);
    await apiFetch("/admin/settings", token, { method: "PUT", body: JSON.stringify(updated) });
    mutate("admin-settings");
    setSaving(false);
  };

  const updateBool = async (key: keyof Settings, value: boolean) => {
    await updateSettings({ ...settings!, [key]: value });
  };

  const updateLookback = async (days: number) => {
    await updateSettings({ ...settings!, gmail_lookback_days: days });
  };

  const moveModel = async (index: number, direction: -1 | 1) => {
    const newOrder = [...settings!.model_priority];
    const target = index + direction;
    if (target < 0 || target >= newOrder.length) return;
    [newOrder[index], newOrder[target]] = [newOrder[target], newOrder[index]];
    await updateSettings({ ...settings!, model_priority: newOrder });
  };


  if (isLoading || !settings) return <p className="text-sm text-gray-400">Chargement des paramètres...</p>;

  return (
    <div className="bg-white border rounded-lg p-6 space-y-6">
      <h3 className="font-semibold text-lg">Paramètres globaux</h3>

      <div className="space-y-3">
        <Toggle
          label="Activer le traitement LLM"
          checked={settings.llm_enabled}
          onChange={(v) => updateBool("llm_enabled", v)}
        />
        <Toggle
          label="Activer le mode Thinking (meilleure qualité, plus lent)"
          checked={settings.thinking_enabled}
          disabled={!settings.llm_enabled}
          onChange={(v) => updateBool("thinking_enabled", v)}
        />
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm text-gray-700">Rétention des articles (scheduler)</span>
          <select
            value={settings.retention_days}
            onChange={(e) => updateSettings({ ...settings!, retention_days: Number(e.target.value) })}
            disabled={saving}
            className="border rounded px-3 py-1 text-sm text-gray-700 bg-white disabled:opacity-50"
          >
            {RETENTION_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d === 0 ? "Illimitée" : d === 1 ? "1 jour" : `${d} jours`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between gap-4">
          <span className="text-sm text-gray-700">Récupération emails Gmail (jours)</span>
          <select
            value={settings.gmail_lookback_days}
            onChange={(e) => updateLookback(Number(e.target.value))}
            disabled={saving}
            className="border rounded px-3 py-1 text-sm text-gray-700 bg-white disabled:opacity-50"
          >
            {LOOKBACK_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d} jour{d > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </div>

      </div>

      <div className="border-t pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-700">Priorité des modèles LLM</p>
          {saving && <span className="text-xs text-gray-400">Sauvegarde...</span>}
        </div>
        <p className="text-xs text-gray-400">Le collector essaie les modèles dans l'ordre. Si le premier échoue (quota, modèle indisponible, erreur d'API), il passe au suivant. La cause exacte de chaque échec figure dans le rapport d'exécution.</p>
        <div className="space-y-2">
          {(settings.model_priority ?? []).map((modelId, i) => {
            const info = MODEL_LABELS[modelId] ?? { label: modelId };
            return (
              <div
                key={modelId}
                className="flex items-center gap-3 px-4 py-2 rounded border border-gray-200"
              >
                <span className="text-gray-400 text-xs w-4 text-center font-mono">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium">{info.label}</span>
                  {info.note && <span className="ml-2 text-xs text-gray-400">{info.note}</span>}
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => moveModel(i, -1)}
                    disabled={i === 0 || saving}
                    className="w-6 h-6 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-20 text-sm"
                  >
                    ▲
                  </button>
                  <button
                    onClick={() => moveModel(i, 1)}
                    disabled={i === (settings.model_priority ?? []).length - 1 || saving}
                    className="w-6 h-6 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-20 text-sm"
                  >
                    ▼
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t pt-4 flex items-center gap-3">
        <button
          onClick={launchCollect}
          disabled={collecting}
          className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
          style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
        >
          {collecting ? "Lancement…" : "▶ Lancer la collecte"}
        </button>
        {collectMsg && (
          <span className="text-sm font-medium" style={{ color: collectMsg.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
            {collectMsg}
          </span>
        )}
      </div>

    </div>
  );
}

function Toggle({ label, checked, disabled = false, onChange }: {
  label: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={`flex items-center justify-between gap-4 ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}>
      <span className="text-sm text-gray-700">{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-colors ${checked ? "bg-blue-600" : "bg-gray-300"}`}
      >
        <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} />
      </button>
    </label>
  );
}
