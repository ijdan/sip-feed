"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

export default function StatsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const token = (session as any)?.accessToken;
  const role = (session as any)?.role;

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && role !== "admin") router.replace("/");
  }, [status, role, router]);

  const { data, isLoading } = useSWR(
    token && role === "admin" ? "admin-stats" : null,
    () => fetch(`${API}/admin/stats`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  );

  if (status === "loading" || isLoading) {
    return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Chargement…</p>;
  }

  if (!data) return null;

  const formatId = (id: string) =>
    id.startsWith("ip:") ? `🌐 ${id.slice(3)}` : `👤 ${id}`;

  return (
    <div className="space-y-8 pb-12">
      <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Statistiques</h1>

      {/* Utilisateurs */}
      <Section title="Utilisateurs enregistrés">
        <div className="text-4xl font-bold" style={{ color: "var(--accent)" }}>
          {data.users_count}
        </div>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>comptes créés</p>
      </Section>

      {/* Activité API */}
      <Section title="Appels API /articles/">
        {data.api_calls.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Aucune donnée encore.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Identifiant", "Aujourd'hui", "7 derniers jours", "30 derniers jours"].map(h => (
                    <th key={h} className="text-left py-2 pr-4 font-medium" style={{ color: "var(--text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.api_calls.map((row: any) => (
                  <tr key={row.identifier} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-2 pr-4 font-mono text-xs" style={{ color: "var(--text)" }}>{formatId(row.identifier)}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.today}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.last_7}</td>
                    <td className="py-2 pr-4 text-center font-semibold" style={{ color: "var(--text)" }}>{row.last_30}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Articles par utilisateur */}
      <Section title="Activité articles par utilisateur">
        {data.user_article_stats.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Aucune donnée encore.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Utilisateur", "⭐ Favoris", "👓 À lire", "✓ Lus", "🗑️ Supprimés"].map(h => (
                    <th key={h} className="text-left py-2 pr-4 font-medium" style={{ color: "var(--text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.user_article_stats.map((row: any) => (
                  <tr key={row.email} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-2 pr-4 text-xs" style={{ color: "var(--text)" }}>👤 {row.email}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.favorites}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.reading_list}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.read_articles}</td>
                    <td className="py-2 pr-4 text-center" style={{ color: "var(--text)" }}>{row.dismissed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border p-6 space-y-4"
      style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
      <h2 className="font-semibold text-lg" style={{ color: "var(--text)" }}>{title}</h2>
      {children}
    </div>
  );
}
