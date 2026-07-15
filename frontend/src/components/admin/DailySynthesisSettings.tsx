"use client";
import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { CATEGORIES } from "@/lib/categories";

interface Settings {
  llm_enabled: boolean;
  thinking_enabled: boolean;
  model_priority: string[];
  gmail_lookback_days: number;
  retention_days: number;
  interest: string;
  synthesis_source_ids: string[];
  synthesis_categories: string[];
  synthesis_max_input_chars: number;
}

const MAX_INPUT_OPTIONS = [30_000, 60_000, 120_000, 180_000, 250_000];
const DEFAULT_MAX_INPUT = 180_000;

interface Source {
  id: string;
  name: string;
  type: string;
  active: boolean;
}

export default function DailySynthesisSettings({ token }: { token: string }) {
  const { data: settings } = useSWR<Settings>(
    "admin-settings",
    () => api.admin.settings(token)
  );
  const { data: sources } = useSWR<Source[]>(
    "sources",
    () => api.sources.list(token)
  );

  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [interest, setInterest] = useState("");
  const [maxInputChars, setMaxInputChars] = useState(DEFAULT_MAX_INPUT);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setSourceIds(settings.synthesis_source_ids ?? []);
    setCategories(settings.synthesis_categories ?? []);
    setInterest(settings.interest ?? "");
    setMaxInputChars(settings.synthesis_max_input_chars ?? DEFAULT_MAX_INPUT);
  }, [settings]);

  const toggleSource = (id: string) =>
    setSourceIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);

  const toggleCategory = (cat: string) =>
    setCategories((prev) => prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]);

  const save = async () => {
    if (!token || !settings) return; // attendre que les settings soient chargés
    setSaving(true);
    setSaveError(false);
    try {
      await api.admin.updateSettings(token, {
        ...settings,
        interest,
        synthesis_source_ids: sourceIds,
        synthesis_categories: categories,
        synthesis_max_input_chars: maxInputChars,
      });
      mutate("admin-settings");
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const activeSources = (sources ?? []).filter((s) => s.active);

  return (
    <div className="bg-white border rounded-lg p-6 space-y-5">
      <div>
        <h3 className="font-semibold text-lg">📰 Synthèse du jour</h3>
        <p className="text-xs text-gray-400 mt-1">
          Après chaque collecte, le LLM produit une synthèse ciblée sur le centre d'intérêt,
          à partir des sources et thèmes sélectionnés. Aucune sélection = tout est considéré.
          Laisser le centre d'intérêt vide pour désactiver la synthèse.
        </p>
      </div>

      {/* Sources à considérer */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-700">Sources à considérer</p>
        {activeSources.length === 0 ? (
          <p className="text-xs text-gray-400">Aucune source active.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {activeSources.map((s) => (
              <Chip
                key={s.id}
                label={s.name}
                selected={sourceIds.includes(s.id)}
                onClick={() => toggleSource(s.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Thèmes */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-700">Thèmes</p>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => (
            <Chip
              key={cat}
              label={cat}
              selected={categories.includes(cat)}
              onClick={() => toggleCategory(cat)}
            />
          ))}
        </div>
      </div>

      {/* Volume max envoyé au LLM */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-700">Volume max envoyé au LLM</p>
          <p className="text-xs text-gray-400">
            Plafond de texte (caractères) transmis à Gemini pour la synthèse — borne la consommation de tokens.
          </p>
        </div>
        <select
          value={maxInputChars}
          onChange={(e) => setMaxInputChars(Number(e.target.value))}
          disabled={saving}
          className="border rounded px-3 py-1 text-sm text-gray-700 bg-white disabled:opacity-50"
        >
          {MAX_INPUT_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n.toLocaleString("fr-FR")} caractères
            </option>
          ))}
        </select>
      </div>

      {/* Centre d'intérêt */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">🎯 Centre d'intérêt</label>
        <div className="flex gap-2">
          <input
            value={interest}
            onChange={(e) => setInterest(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && save()}
            placeholder="Ex: SDLC à l'aune de l'IA"
            className="flex-1 border rounded px-3 py-2 text-sm text-gray-700 bg-white"
          />
          <button
            onClick={save}
            disabled={saving || !settings}
            title={!settings ? "Chargement des paramètres…" : undefined}
            className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
            style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
          >
            {saving ? "…" : !settings ? "Chargement…" : "Sauvegarder"}
          </button>
          {saved && <span className="text-sm font-medium self-center" style={{ color: "#22c55e" }}>✓ Sauvegardé</span>}
          {saveError && <span className="text-sm font-medium self-center" style={{ color: "#ef4444" }}>✗ Erreur</span>}
        </div>
      </div>
    </div>
  );
}

function Chip({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={selected}
      className={`text-xs px-3 py-1.5 rounded-full border transition ${
        selected
          ? "bg-blue-600 border-blue-600 text-white"
          : "bg-white border-gray-300 text-gray-600 hover:border-gray-400"
      }`}
    >
      {selected ? "✓ " : ""}{label}
    </button>
  );
}
