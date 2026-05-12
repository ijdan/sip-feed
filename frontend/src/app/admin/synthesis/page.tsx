"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
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
