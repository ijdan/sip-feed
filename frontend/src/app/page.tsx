"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import NewsCard from "@/components/NewsCard";
import CategoryFilter from "@/components/CategoryFilter";
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

  useEffect(() => {
    const savedCols = localStorage.getItem("feed-columns");
    if (savedCols) setColumns(Number(savedCols));
    const savedLang = localStorage.getItem("feed-lang");
    if (savedLang === "en" || savedLang === "fr") setLang(savedLang);
  }, []);

  const changeColumns = (n: number) => {
    setColumns(n);
    localStorage.setItem("feed-columns", String(n));
  };

  const changeLang = (l: "fr" | "en") => {
    setLang(l);
    localStorage.setItem("feed-lang", l);
  };

  const articlesUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/${category ? "?category=" + category : ""}`;
  const statsUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/stats`;

  const { data, isLoading } = useSWR(articlesUrl, fetcher);
  const { data: stats } = useSWR(statsUrl, fetcher);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <p className="text-sm text-gray-500">
          {stats ? `${stats.total} article${stats.total > 1 ? "s" : ""}` : ""}
        </p>
        <div className="flex items-center gap-2">
          {/* Sélecteur de langue */}
          <div className="flex border rounded-md overflow-hidden">
            {(["fr", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => changeLang(l)}
                className={`px-3 py-1 text-sm font-medium transition ${
                  lang === l ? "bg-gray-900 text-white" : "bg-white text-gray-500 hover:bg-gray-100"
                }`}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          {/* Sélecteur de colonnes */}
          <div className="flex border rounded-md overflow-hidden">
            {[1, 2, 3].map((n) => (
              <button
                key={n}
                onClick={() => changeColumns(n)}
                title={`${n} colonne${n > 1 ? "s" : ""}`}
                className={`px-3 py-1 text-sm transition ${
                  columns === n ? "bg-gray-900 text-white" : "bg-white text-gray-500 hover:bg-gray-100"
                }`}
              >
                {n === 1 ? "▬" : n === 2 ? "⊟" : "⊞"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <CategoryFilter
        categories={CATEGORIES}
        selected={category}
        onChange={setCategory}
        counts={stats?.by_category ?? {}}
        lang={lang}
      />

      {isLoading && <p className="text-gray-500">Chargement...</p>}
      {!isLoading && data?.items?.length === 0 && (
        <p className="text-gray-400 text-sm">Aucun article dans cette catégorie.</p>
      )}

      <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
        {data?.items?.map((article: any) => (
          <NewsCard key={article.id} article={article} lang={lang} />
        ))}
      </div>
    </div>
  );
}
