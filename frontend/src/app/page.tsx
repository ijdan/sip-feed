"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import NewsCard from "@/components/NewsCard";
import CategoryFilter from "@/components/CategoryFilter";

const CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"];

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function FeedPage() {
  const [category, setCategory] = useState<string | null>(null);

  const params = category ? { category } : undefined;
  const articlesUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/${params ? "?category=" + params.category : ""}`;
  const statsUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/stats`;

  const { data, isLoading } = useSWR(articlesUrl, fetcher);
  const { data: stats } = useSWR(statsUrl, fetcher);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {stats ? `${stats.total} article${stats.total > 1 ? "s" : ""} au total` : ""}
        </p>
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
      {data?.items?.map((article: any) => (
        <NewsCard key={article.id} article={article} />
      ))}
    </div>
  );
}
