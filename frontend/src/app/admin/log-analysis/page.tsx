"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

const PRIORITE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  CRITIQUE: { label: "CRITIQUE", color: "#dc2626", bg: "#fef2f2" },
  HAUTE:    { label: "HAUTE",    color: "#ea580c", bg: "#fff7ed" },
  MOYENNE:  { label: "MOYENNE",  color: "#ca8a04", bg: "#fefce8" },
  BASSE:    { label: "BASSE",    color: "#6b7280", bg: "#f9fafb" },
};

function PrioriteBadge({ priorite }: { priorite: string }) {
  const cfg = PRIORITE_CONFIG[priorite] ?? PRIORITE_CONFIG.BASSE;
  return (
    <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
      style={{ color: cfg.color, backgroundColor: cfg.bg }}>
      {cfg.label}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy}
      className="text-xs px-3 py-1.5 rounded border transition hover:opacity-70 shrink-0"
      style={{ borderColor: "var(--border)", color: "var(--text-muted)", backgroundColor: "var(--surface-2)" }}>
      {copied ? "✓ Copié !" : "Copier le prompt"}
    </button>
  );
}

export default function LogAnalysisPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const token = ((session as unknown) as import("@/lib/types").AppSession)?.accessToken;
  const role = ((session as unknown) as import("@/lib/types").AppSession)?.role;

  const today = new Date().toISOString().slice(0, 10);
  // Le rapport du jour couvre la veille (le job tourne la nuit et écrit log_analyses/{hier})
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const [selectedDate, setSelectedDate] = useState(yesterday);

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && role !== "admin") router.replace("/");
  }, [status, role, router]);

  const swrKey = token && role === "admin"
    ? `log-analysis-${selectedDate}`
    : null;

  const { data, isLoading, error, mutate } = useSWR(swrKey, () =>
    fetch(`${API}/admin/log-analysis/${selectedDate}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(async r => {
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
  );

  if (status === "loading" || isLoading) {
    return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Chargement…</p>;
  }

  const items: any[] = data?.items ?? [];

  return (
    <div className="space-y-6 pb-12">
      {/* En-tête */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Analyse des logs</h1>
        <div className="flex items-center gap-3">
          <input
            type="date"
            value={selectedDate}
            max={today}
            onChange={e => setSelectedDate(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm"
            style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
          />
          <button onClick={() => mutate()}
            className="text-sm hover:underline"
            style={{ color: "var(--text-muted)" }}>
            Rafraîchir
          </button>
        </div>
      </div>

      {/* Erreur réseau */}
      {error && (
        <div className="rounded-xl border p-5 text-sm"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)", color: "#dc2626" }}>
          Service temporairement indisponible.
        </div>
      )}

      {/* Pas de rapport */}
      {!error && data === null && (
        <div className="rounded-xl border p-8 text-center"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2" style={{ color: "var(--text)" }}>
            Aucun rapport disponible pour cette date
          </p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Le job log-analyzer tourne chaque nuit à 05h00.
          </p>
        </div>
      )}

      {/* Rapport disponible */}
      {data && (
        <>
          {/* Résumé */}
          <div className="rounded-xl border p-5 space-y-1"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {data.date}
                {" · "}{data.logs_count} entrée{data.logs_count !== 1 ? "s" : ""} analysée{data.logs_count !== 1 ? "s" : ""}
                {" · "}Généré le {new Date(data.generated_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
              </p>
            </div>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{data.resume}</p>
          </div>

          {/* Aucune anomalie */}
          {items.length === 0 && (
            <div className="rounded-xl border p-8 text-center"
              style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
              <p className="text-2xl mb-2">✅</p>
              <p className="font-medium" style={{ color: "var(--text)" }}>Aucune anomalie détectée</p>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Tous les services fonctionnent normalement sur cette période.
              </p>
            </div>
          )}

          {/* Liste des items */}
          {items.length > 0 && (
            <div className="space-y-3">
              {items.map((item: any, i: number) => (
                <div key={i} className="rounded-xl border p-5 space-y-3"
                  style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      <PrioriteBadge priorite={item.priorite} />
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {item.date ? new Date(item.date).toLocaleString("fr-FR", {
                          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"
                        }) : ""}
                      </span>
                    </div>
                    <CopyButton text={item.prompt_correction} />
                  </div>
                  <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                    {item.point_notable}
                  </p>
                  <div className="rounded-lg p-3 text-xs leading-relaxed overflow-auto max-h-40"
                    style={{ backgroundColor: "var(--surface-2)", color: "var(--text-muted)", fontFamily: "monospace" }}>
                    {item.prompt_correction}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
