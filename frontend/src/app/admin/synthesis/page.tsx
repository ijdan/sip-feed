"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

export default function SynthesisPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const token = (session as any)?.accessToken;
  const role = (session as any)?.role;

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && role !== "admin") router.replace("/");
  }, [status, role, router]);

  const { data, isLoading, mutate } = useSWR(
    token && role === "admin" ? "admin-syntheses" : null,
    () => fetch(`${API}/admin/syntheses`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  );

  // Partage le même cache SWR que AdminSettings pour éviter les doublons
  const { data: settingsData, mutate: mutateSettings } = useSWR(
    token && role === "admin" ? "admin-settings" : null,
    () => fetch(`${API}/admin/settings`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  );

  const [interest, setInterest] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);

  useEffect(() => {
    if (settingsData?.interest !== undefined) setInterest(settingsData.interest);
  }, [settingsData]);

  const saveInterest = async () => {
    if (!token || !settingsData) return; // attendre que les settings soient chargés
    setSaving(true);
    setSaveError(false);
    try {
      const res = await fetch(`${API}/admin/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...settingsData, interest }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      mutateSettings();
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  if (status === "loading" || isLoading) {
    return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Chargement…</p>;
  }

  const syntheses = data?.syntheses ?? [];

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Synthèse</h1>
        <button onClick={() => mutate()}
          className="text-sm hover:underline"
          style={{ color: "var(--text-muted)" }}>
          Rafraîchir
        </button>
      </div>

      {/* Centre d'intérêt */}
      <div className="rounded-xl border p-5 space-y-3"
        style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <div>
          <label className="block text-sm font-medium mb-1" style={{ color: "var(--text)" }}>
            🎯 Centre d'intérêt
          </label>
          <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
            Après chaque collecte, le LLM produira une synthèse ciblée sur ce sujet.
            Laisser vide pour désactiver.
          </p>
          <div className="flex gap-2">
            <input
              value={interest}
              onChange={(e) => setInterest(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveInterest()}
              placeholder="Ex: SDLC à l'aune de l'IA"
              className="flex-1 border rounded px-3 py-2 text-sm"
              style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
            />
            <button
              onClick={saveInterest}
              disabled={saving || !settingsData}
              title={!settingsData ? "Chargement des paramètres…" : undefined}
              className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
              style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
            >
              {saving ? "…" : !settingsData ? "Chargement…" : "Sauvegarder"}
            </button>
            {saved && <span className="text-sm font-medium" style={{ color: "#22c55e" }}>✓ Sauvegardé</span>}
            {saveError && <span className="text-sm font-medium" style={{ color: "#ef4444" }}>✗ Erreur</span>}
          </div>
        </div>
      </div>

      {syntheses.length === 0 ? (
        <div className="rounded-xl border p-8 text-center"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2" style={{ color: "var(--text)" }}>Aucune synthèse disponible</p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Renseignez un centre d'intérêt dans les paramètres admin et lancez une collecte.
          </p>
        </div>
      ) : (
        syntheses.map((s: any) => (
          <div key={s.date} className="rounded-xl border overflow-hidden"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            {/* En-tête */}
            <div className="px-6 py-4 border-b flex items-center justify-between"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}>
              <div>
                <p className="font-semibold" style={{ color: "var(--text)" }}>🎯 {s.interest}</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {new Date(s.date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
                  {" · "}{s.articles_count} articles analysés
                  {" · "}{new Date(s.generated_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            </div>
            {/* Contenu */}
            <div className="px-6 py-5 prose prose-sm max-w-none text-sm leading-relaxed whitespace-pre-wrap"
              style={{ color: "var(--text)" }}>
              {s.content === "⚠️ Synthèse indisponible — quota LLM épuisé."
                ? <p style={{ color: "var(--text-muted)" }}>⚠️ Synthèse indisponible — quota LLM épuisé lors de cette exécution.</p>
                : s.content}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
