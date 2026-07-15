"use client";
import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import Link from "next/link";
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

const todayISO = () => new Date().toISOString().slice(0, 10);

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

  // Persiste la section telle qu'affichée (utilisé par Sauvegarder et par Générer)
  const persist = async () => {
    await api.admin.updateSettings(token, {
      ...settings,
      interest,
      synthesis_source_ids: sourceIds,
      synthesis_categories: categories,
      synthesis_max_input_chars: maxInputChars,
    });
    mutate("admin-settings");
  };

  const save = async () => {
    if (!token || !settings) return; // attendre que les settings soient chargés
    setSaving(true);
    setSaveError(false);
    try {
      await persist();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const [generating, setGenerating] = useState(false);
  const [generateMsg, setGenerateMsg] = useState("");
  const [generateDone, setGenerateDone] = useState(false);
  const [synthesisDate, setSynthesisDate] = useState(todayISO());

  const launchGeneration = async () => {
    if (!token || !settings || generating) return;
    setGenerating(true);
    setGenerateDone(false);
    const targetDate = synthesisDate || todayISO();
    try {
      if (!interest.trim()) {
        throw new Error("Renseignez un centre d'intérêt avant de générer.");
      }
      // Sauvegarde le périmètre affiché pour que la génération l'utilise
      setGenerateMsg("Sauvegarde du périmètre…");
      await persist();

      const before = (await api.admin.syntheses(token, targetDate))?.syntheses?.[0]?.generated_at ?? null;
      await api.admin.generateSynthesis(token, targetDate);
      setGenerateMsg(`Génération pour le ${targetDate} en cours… (~1 à 2 min)`);

      // Le job est asynchrone : on re-interroge la date ciblée jusqu'à voir
      // une synthèse plus récente (toutes les 10 s, abandon après 5 min).
      const startedAt = Date.now();
      const poll = async () => {
        try {
          const fresh = await api.admin.syntheses(token, targetDate);
          const latest = fresh?.syntheses?.[0]?.generated_at ?? null;
          if (latest && latest !== before) {
            setGenerating(false);
            setGenerateDone(true);
            setGenerateMsg("✓ Synthèse générée");
            return;
          }
        } catch { /* erreur réseau transitoire : on retentera au tick suivant */ }
        if (Date.now() - startedAt > 5 * 60_000) {
          setGenerating(false);
          setGenerateMsg("⚠️ Pas de nouvelle synthèse après 5 min — consultez le rapport de run.");
          setTimeout(() => setGenerateMsg(""), 8000);
          return;
        }
        setTimeout(poll, 10_000);
      };
      setTimeout(poll, 10_000);
    } catch (err: any) {
      setGenerating(false);
      setGenerateMsg(`✗ ${err.message || "Erreur lors du déclenchement"}`);
      setTimeout(() => setGenerateMsg(""), 6000);
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

      {/* Génération manuelle */}
      <div className="border-t pt-4 flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          Date de la synthèse
          <input
            type="date"
            value={synthesisDate}
            max={todayISO()}
            onChange={(e) => setSynthesisDate(e.target.value)}
            disabled={generating}
            className="border rounded px-2 py-1.5 text-sm text-gray-700 bg-white disabled:opacity-50"
          />
        </label>
        <button
          onClick={launchGeneration}
          disabled={generating || !settings}
          title="Sauvegarde le périmètre affiché puis génère la synthèse de la date choisie, sans lancer de collecte (consomme des tokens LLM)"
          className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
          style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
        >
          {generating ? "Génération…" : "⚡ Générer la synthèse"}
        </button>
        {generateMsg && (
          <span className="text-sm font-medium"
            style={{ color: generateMsg.startsWith("✓") ? "#22c55e"
              : generateMsg.startsWith("✗") ? "#ef4444" : "var(--text-muted)" }}>
            {generating && <span className="inline-block animate-spin mr-1">⟳</span>}
            {generateMsg}
          </span>
        )}
        {generateDone && (
          <Link href={`/admin/synthesis?date=${synthesisDate || todayISO()}`}
            className="text-sm font-medium hover:underline"
            style={{ color: "var(--accent)" }}>
            Voir la synthèse →
          </Link>
        )}
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
