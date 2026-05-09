"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import NewsCard from "@/components/NewsCard";
import CategoryFilter from "@/components/CategoryFilter";
import SourceFilter from "@/components/SourceFilter";
import { CATEGORIES } from "@/lib/categories";
const fetcher = (url: string) => fetch(url).then((r) => r.json());

const COLUMN_CLASSES: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
};

export default function FeedPage() {
  const [category, setCategory] = useState<string | null>(null);
  const [columns, setColumns] = useState<number>(1);
  const [lang, setLang] = useState<"fr" | "en">("fr");
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());

  useEffect(() => {
    const savedCols = localStorage.getItem("feed-columns");
    if (savedCols) setColumns(Number(savedCols));
    const savedLang = localStorage.getItem("feed-lang");
    if (savedLang === "en" || savedLang === "fr") setLang(savedLang);
    const savedExcluded = localStorage.getItem("feed-excluded-sources");
    if (savedExcluded) setExcludedSources(new Set(JSON.parse(savedExcluded)));
  }, []);

  const changeColumns = (n: number) => {
    setColumns(n);
    localStorage.setItem("feed-columns", String(n));
  };

  const changeLang = (l: "fr" | "en") => {
    setLang(l);
    localStorage.setItem("feed-lang", l);
  };

  const toggleSource = (source: string) => {
    const next = new Set(excludedSources);
    if (next.has(source)) next.delete(source);
    else next.add(source);
    setExcludedSources(next);
    localStorage.setItem("feed-excluded-sources", JSON.stringify([...next]));
  };

  const articlesUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/${category ? "?category=" + category : ""}`;
  const statsUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/stats`;

  const { data, isLoading } = useSWR(articlesUrl, fetcher);
  const { data: stats } = useSWR(statsUrl, fetcher);

  // Sources uniques présentes dans les articles
  const availableSources: string[] = data?.items
    ? [...new Set<string>(data.items.map((a: any) => a.source_name))].sort()
    : [];

  // Articles filtrés (exclusion des sources désactivées)
  const filteredItems = (data?.items ?? []).filter(
    (a: any) => !excludedSources.has(a.source_name)
  );

  // Compteurs recalculés sur les articles visibles
  const filteredTotal = filteredItems.length;
  const filteredByCategory = filteredItems.reduce((acc: Record<string, number>, a: any) => {
    acc[a.category] = (acc[a.category] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {data ? `${filteredTotal} article${filteredTotal > 1 ? "s" : ""}${excludedSources.size > 0 ? ` (${excludedSources.size} source${excludedSources.size > 1 ? "s" : ""} masquée${excludedSources.size > 1 ? "s" : ""})` : ""}` : ""}
        </p>
        <div className="flex items-center gap-2">
          {/* Sélecteur de langue */}
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {(["fr", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => changeLang(l)}
                className="px-3 py-1 text-sm font-medium transition"
                style={lang === l
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }
                }
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          {/* Sélecteur de colonnes */}
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {[1, 2, 3].map((n) => (
              <button
                key={n}
                onClick={() => changeColumns(n)}
                title={`${n} colonne${n > 1 ? "s" : ""}`}
                className="px-3 py-1 text-sm transition"
                style={columns === n
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }
                }
              >
                {n === 1 ? "▬" : n === 2 ? "⊟" : "⊞"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <SourceFilter
        sources={availableSources}
        excluded={excludedSources}
        onToggle={toggleSource}
      />

      <CategoryFilter
        categories={CATEGORIES}
        selected={category}
        onChange={setCategory}
        counts={filteredByCategory}
        lang={lang}
      />

      {isLoading && <p className="text-gray-500">Chargement...</p>}
      {!isLoading && filteredItems.length === 0 && (
        <p className="text-gray-400 text-sm">Aucun article — toutes les sources sont masquées ou aucun article dans cette catégorie.</p>
      )}

      <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
        {filteredItems.map((article: any) => (
          <NewsCard key={article.id} article={article} lang={lang} />
        ))}
      </div>
    </div>
  );
}
