"use client";
import { useState } from "react";
import useSWR, { mutate } from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

async function apiFetch(path: string, token: string, options: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options.headers },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

interface Settings {
  llm_enabled: boolean;
  translation_enabled: boolean;
}

export default function AdminSettings({ token }: { token: string }) {
  const { data: settings, isLoading } = useSWR<Settings>(
    "admin-settings",
    () => apiFetch("/admin/settings", token)
  );
  const [purging, setPurging] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const updateSetting = async (key: keyof Settings, value: boolean) => {
    const updated = { ...settings!, [key]: value };
    if (key === "llm_enabled" && !value) updated.translation_enabled = false;
    await apiFetch("/admin/settings", token, { method: "PUT", body: JSON.stringify(updated) });
    mutate("admin-settings");
  };

  const handlePurgeAndCollect = async () => {
    if (!confirm) { setConfirm(true); return; }
    setConfirm(false);
    setPurging(true);
    try {
      await apiFetch("/admin/purge-and-collect", token, { method: "POST" });
      alert("Purge et collecte lancées !");
    } catch {
      alert("Erreur lors du lancement.");
    }
    setPurging(false);
    setCollecting(false);
  };

  if (isLoading || !settings) return <p className="text-sm text-gray-400">Chargement des paramètres...</p>;

  return (
    <div className="bg-white border rounded-lg p-6 space-y-5">
      <h3 className="font-semibold text-lg">Paramètres globaux</h3>

      <div className="space-y-3">
        <Toggle
          label="Activer le traitement LLM (Gemini)"
          checked={settings.llm_enabled}
          onChange={(v) => updateSetting("llm_enabled", v)}
        />
        <Toggle
          label="Activer la traduction en français"
          checked={settings.translation_enabled}
          disabled={!settings.llm_enabled}
          onChange={(v) => updateSetting("translation_enabled", v)}
        />
      </div>

      <div className="border-t pt-4">
        <p className="text-sm text-gray-500 mb-3">
          Lance une collecte complète en repartant de zéro (purge tous les articles existants).
        </p>
        <button
          onClick={handlePurgeAndCollect}
          disabled={purging || collecting}
          className={`px-4 py-2 rounded text-sm font-medium transition ${
            confirm
              ? "bg-red-600 text-white hover:bg-red-700"
              : "bg-gray-900 text-white hover:bg-gray-700"
          } disabled:opacity-50`}
        >
          {purging ? "Purge en cours..." : collecting ? "Collecte lancée..." : confirm ? "Confirmer la purge ?" : "Forcer la récupération"}
        </button>
        {confirm && (
          <button onClick={() => setConfirm(false)} className="ml-3 text-sm text-gray-500 hover:underline">
            Annuler
          </button>
        )}
      </div>
    </div>
  );
}

function Toggle({ label, checked, disabled = false, onChange }: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className={`flex items-center justify-between gap-4 ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}>
      <span className="text-sm text-gray-700">{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-colors ${checked ? "bg-blue-600" : "bg-gray-300"} ${disabled ? "cursor-not-allowed" : ""}`}
      >
        <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} />
      </button>
    </label>
  );
}
