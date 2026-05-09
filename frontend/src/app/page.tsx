"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import NewsCard from "@/components/NewsCard";
import CategoryFilter from "@/components/CategoryFilter";

const CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"];
const fetcher = (url: string) => fetch(url).then((r) => r.json());

const COLUMN_CLASSES: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
};

export default function FeedPage() {
  const [category, setCategory] = useState<string | null>(null);
  const [columns, setColumns] = useState<number>(1);

  useEffect(() => {
    const saved = localStorage.getItem("feed-columns");
    if (saved) setColumns(Number(saved));
  }, []);

  const changeColumns = (n: number) => {
    setColumns(n);
    localStorage.setItem("feed-columns", String(n));
  };

  const articlesUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/${category ? "?category=" + category : ""}`;
  const statsUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/stats`;

  const { data, isLoading } = useSWR(articlesUrl, fetcher);
  const { data: stats } = useSWR(statsUrl, fetcher);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {stats ? `${stats.total} article${stats.total > 1 ? "s" : ""}` : ""}
        </p>
        <div className="flex items-center gap-1 border rounded-md overflow-hidden">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              onClick={() => changeColumns(n)}
              title={`${n} colonne${n > 1 ? "s" : ""}`}
              className={`px-3 py-1 text-sm transition ${
                columns === n
                  ? "bg-gray-900 text-white"
                  : "bg-white text-gray-500 hover:bg-gray-100"
              }`}
            >
              {n === 1 ? "▬" : n === 2 ? "⊟" : "⊞"}
            </button>
          ))}
        </div>
      </div>

      <CategoryFilter
        categories={CATEGORIES}
        selected={category}
        onChange={setCategory}
        counts={stats?.by_category ?? {}}
      />

      {isLoading && <p className="text-gray-500">Chargement...</p>}
      {!isLoading && data?.items?.length === 0 && (
        <p className="text-gray-400 text-sm">Aucun article dans cette catégorie.</p>
      )}

      <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
        {data?.items?.map((article: any) => (
          <NewsCard key={article.id} article={article} />
        ))}
      </div>
    </div>
  );
}
