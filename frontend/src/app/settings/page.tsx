"use client";
import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useSettings } from "@/lib/useSettings";
import { CATEGORIES, categoryLabel } from "@/lib/categories";

const API = process.env.NEXT_PUBLIC_API_URL;
const fetcher = (url: string) => fetch(url).then(r => r.json());

const FONT_LABELS: Record<string, string> = { sm: "Petite", md: "Moyenne", lg: "Grande" };

export default function SettingsPage() {
  const { data: session, status } = useSession();
  const token = (session as any)?.accessToken as string | undefined;
  const router = useRouter();
  const { settings, update } = useSettings();
  const [sources, setSources] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") { router.replace("/login"); return; }
    // Charger les sources disponibles depuis les articles
    fetch(`${API}/articles/?page_size=500`)
      .then(r => r.json())
      .then(data => {
        const unique = Array.from(new Set<string>(data.items?.map((a: any) => a.source_name) ?? [])).sort();
        setSources(unique as string[]);
      });
  }, [status, router]);

  const toggle = (field: "excluded_categories" | "excluded_sources", key: string) => {
    const current = settings[field] as string[];
    const next = current.includes(key) ? current.filter(k => k !== key) : [...current, key];
    update({ [field]: next });
    flash();
  };

  const flash = () => { setSaved(true); setTimeout(() => setSaved(false), 1500); };

  if (status === "loading") return null;

  return (
    <div className="max-w-lg mx-auto mt-8 space-y-5 pb-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Paramètres</h1>
        {saved && <span className="text-sm text-green-500">✓ Sauvegardé</span>}
      </div>

      {/* Affichage */}
      <Section title="Affichage">
        <Row label="Mode">
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {(["light", "dark"] as const).map(t => (
              <button key={t} onClick={() => { update({ theme: t }); flash(); }}
                className="px-3 py-1.5 text-sm transition"
                style={settings.theme === t
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }}>
                {t === "light" ? "☀️ Clair" : "🌙 Sombre"}
              </button>
            ))}
          </div>
        </Row>
        <Row label="Colonnes">
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {([1, 2, 3] as const).map(n => (
              <button key={n} onClick={() => { update({ columns: n }); flash(); }}
                className="px-3 py-1.5 text-sm transition"
                style={settings.columns === n
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }}>
                {n === 1 ? "▬" : n === 2 ? "⊟" : "⊞"}
              </button>
            ))}
          </div>
        </Row>
        <Row label="Police">
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {(["sm", "md", "lg"] as const).map((f, i) => (
              <button key={f} onClick={() => { update({ font_size: f }); flash(); }}
                className="px-3 py-1.5 transition"
                style={{
                  fontSize: [12, 15, 19][i],
                  ...(settings.font_size === f
                    ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                    : { backgroundColor: "var(--surface)", color: "var(--text-muted)" })
                }}>
                A
              </button>
            ))}
          </div>
        </Row>
      </Section>

      {/* Catégories par défaut */}
      <Section title="Catégories affichées par défaut">
        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
          Les catégories décochées seront masquées par défaut dans le feed.
        </p>
        <div className="space-y-1">
          {CATEGORIES.map(cat => (
            <label key={cat} className="flex items-center gap-3 py-1 cursor-pointer text-sm"
              style={{ color: "var(--text)" }}>
              <input type="checkbox"
                checked={!settings.excluded_categories.includes(cat)}
                onChange={() => toggle("excluded_categories", cat)}
                className="w-4 h-4" />
              {categoryLabel(cat, "fr")}
            </label>
          ))}
        </div>
      </Section>

      {/* Sources par défaut */}
      <Section title="Sources affichées par défaut">
        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
          Les sources décochées seront masquées par défaut dans le feed.
        </p>
        {sources.length === 0
          ? <p className="text-sm" style={{ color: "var(--text-muted)" }}>Chargement…</p>
          : <div className="space-y-1">
              {sources.map(src => (
                <label key={src} className="flex items-center gap-3 py-1 cursor-pointer text-sm"
                  style={{ color: "var(--text)" }}>
                  <input type="checkbox"
                    checked={!settings.excluded_sources.includes(src)}
                    onChange={() => toggle("excluded_sources", src)}
                    className="w-4 h-4" />
                  {src}
                </label>
              ))}
            </div>
        }
      </Section>

    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border p-5 space-y-4"
      style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
      <h2 className="font-semibold" style={{ color: "var(--text)" }}>{title}</h2>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm" style={{ color: "var(--text-muted)" }}>{label}</span>
      {children}
    </div>
  );
}
