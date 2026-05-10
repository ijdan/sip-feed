"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import NewsCard from "@/components/NewsCard";
import DropdownFilter, { FilterItem } from "@/components/DropdownFilter";
import RadioFilter from "@/components/RadioFilter";
import { CATEGORIES, categoryLabel } from "@/lib/categories";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const COLUMN_CLASSES: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
};

export default function FeedPage() {
  const [columns, setColumns] = useState<number>(1);
  const [lang, setLang] = useState<"fr" | "en">("fr");
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [dismissedList, setDismissedList] = useState<string[]>([]);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [readingList, setReadingList] = useState<Set<string>>(new Set());
  const [filterFavorites, setFilterFavorites] = useState(false);
  const [filterReading, setFilterReading] = useState(false);

  useEffect(() => {
    const savedCols = localStorage.getItem("feed-columns");
    if (savedCols) setColumns(Number(savedCols));
    const savedLang = localStorage.getItem("feed-lang");
    if (savedLang === "en" || savedLang === "fr") setLang(savedLang);
    const savedExcSrc = localStorage.getItem("feed-excluded-sources");
    if (savedExcSrc) setExcludedSources(new Set(JSON.parse(savedExcSrc)));
    const savedCat = localStorage.getItem("feed-selected-category");
    if (savedCat) setSelectedCategory(savedCat);
    const savedDismissed = localStorage.getItem("feed-dismissed");
    if (savedDismissed) setDismissedList(JSON.parse(savedDismissed));
    const savedFav = localStorage.getItem("feed-favorites");
    if (savedFav) setFavorites(new Set(JSON.parse(savedFav)));
    const savedRL = localStorage.getItem("feed-reading-list");
    if (savedRL) setReadingList(new Set(JSON.parse(savedRL)));
  }, []);

  const changeColumns = (n: number) => {
    setColumns(n);
    localStorage.setItem("feed-columns", String(n));
  };

  const changeLang = (l: "fr" | "en") => {
    setLang(l);
    localStorage.setItem("feed-lang", l);
  };

  const toggleSource = (key: string) => {
    const next = new Set(excludedSources);
    next.has(key) ? next.delete(key) : next.add(key);
    setExcludedSources(next);
    localStorage.setItem("feed-excluded-sources", JSON.stringify(Array.from(next)));
  };

  const selectCategory = (key: string | null) => {
    setSelectedCategory(key);
    if (key) localStorage.setItem("feed-selected-category", key);
    else localStorage.removeItem("feed-selected-category");
  };

  const dismissedSet = new Set(dismissedList);

  const dismissArticle = (id: string) => {
    if (dismissedSet.has(id)) return;
    const next = [...dismissedList, id];
    setDismissedList(next);
    localStorage.setItem("feed-dismissed", JSON.stringify(next));
  };

  const undoDismiss = () => {
    const next = dismissedList.slice(0, -1);
    setDismissedList(next);
    localStorage.setItem("feed-dismissed", JSON.stringify(next));
  };

  const toggleFavorite = (id: string) => {
    const next = new Set(favorites);
    next.has(id) ? next.delete(id) : next.add(id);
    setFavorites(next);
    localStorage.setItem("feed-favorites", JSON.stringify(Array.from(next)));
  };

  const toggleReadingList = (id: string) => {
    const next = new Set(readingList);
    next.has(id) ? next.delete(id) : next.add(id);
    setReadingList(next);
    localStorage.setItem("feed-reading-list", JSON.stringify(Array.from(next)));
  };


  const articlesUrl = `${process.env.NEXT_PUBLIC_API_URL}/articles/?page_size=500`;
  const { data, isLoading } = useSWR(articlesUrl, fetcher);

  // Sources uniques avec compteurs
  const sourceCountsAll: Record<string, number> = (data?.items ?? []).reduce(
    (acc: Record<string, number>, a: any) => {
      acc[a.source_name] = (acc[a.source_name] ?? 0) + 1;
      return acc;
    }, {}
  );
  const sourceItems: FilterItem[] = Object.entries(sourceCountsAll)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, count]) => ({ key, label: key, count }));

  // Catégories avec compteurs
  const categoryItems: FilterItem[] = CATEGORIES.map((cat) => ({
    key: cat,
    label: categoryLabel(cat, lang),
    count: (data?.items ?? []).filter((a: any) => a.category === cat).length,
  }));

  // Articles filtrés
  const filteredItems = (data?.items ?? []).filter(
    (a: any) =>
      !excludedSources.has(a.source_name) &&
      (selectedCategory === null || a.category === selectedCategory) &&
      !dismissedSet.has(a.id) &&
      (!filterFavorites || favorites.has(a.id)) &&
      (!filterReading || readingList.has(a.id))
  );

  const filteredTotal = filteredItems.length;
  const totalAll = data?.total ?? 0;
  const hasFilters = excludedSources.size > 0 || selectedCategory !== null || filterFavorites || filterReading;

  return (
    <div className="space-y-4">

      {/* Ligne 1 : compteur + undo + contrôles */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          {dismissedList.length > 0 && (
            <button
              onClick={undoDismiss}
              title={`Réafficher le dernier article masqué (${dismissedList.length})`}
              className="flex items-center gap-1 px-2 py-1 rounded-md border text-sm transition"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
            >
              ↩ <span className="text-xs opacity-70">{dismissedList.length}</span>
            </button>
          )}
          <span>
            {isLoading ? "…" : hasFilters
              ? `${filteredTotal} sur ${totalAll} article${totalAll > 1 ? "s" : ""}`
              : `${totalAll} article${totalAll > 1 ? "s" : ""}`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Langue */}
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {(["fr", "en"] as const).map((l) => (
              <button key={l} onClick={() => changeLang(l)}
                className="px-3 py-1 text-sm font-medium transition"
                style={lang === l
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Colonnes */}
          <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
            {[1, 2, 3].map((n) => (
              <button key={n} onClick={() => changeColumns(n)}
                title={`${n} colonne${n > 1 ? "s" : ""}`}
                className="px-3 py-1 text-sm transition"
                style={columns === n
                  ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                  : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }}>
                {n === 1 ? "▬" : n === 2 ? "⊟" : "⊞"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Ligne 2 : filtres dropdown + favoris/lecture */}
      <div className="flex items-center gap-2 flex-wrap">
        <DropdownFilter
          label="Sources"
          items={sourceItems}
          excluded={excludedSources}
          onToggle={toggleSource}
        />
        <RadioFilter
          label="Catégories"
          items={categoryItems}
          selected={selectedCategory}
          onSelect={selectCategory}
          allLabel="Toutes"
        />
        <div className="flex gap-1 ml-1">
          <button
            onClick={() => setFilterFavorites(f => !f)}
            title={`Favoris (${favorites.size})`}
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={{
              borderColor: filterFavorites ? "var(--accent)" : "var(--border)",
              backgroundColor: filterFavorites ? "var(--accent)" : "var(--surface)",
              color: filterFavorites ? "var(--bg)" : favorites.size > 0 ? "var(--text)" : "var(--text-muted)",
              opacity: favorites.size === 0 && !filterFavorites ? 0.4 : 1,
            }}
          >
            ⭐{favorites.size > 0 && <span className="ml-1 text-xs">{favorites.size}</span>}
          </button>
          <button
            onClick={() => setFilterReading(r => !r)}
            title={`Liste de lecture (${readingList.size})`}
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={{
              borderColor: filterReading ? "var(--accent)" : "var(--border)",
              backgroundColor: filterReading ? "var(--accent)" : "var(--surface)",
              color: filterReading ? "var(--bg)" : readingList.size > 0 ? "var(--text)" : "var(--text-muted)",
              opacity: readingList.size === 0 && !filterReading ? 0.4 : 1,
            }}
          >
            👓{readingList.size > 0 && <span className="ml-1 text-xs">{readingList.size}</span>}
          </button>
        </div>
      </div>

      {/* Feed */}
      {isLoading && <p style={{ color: "var(--text-muted)" }}>Chargement…</p>}
      {!isLoading && filteredItems.length === 0 && (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Aucun article — ajuste les filtres ou réaffiche des sources.
        </p>
      )}

      <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
        {filteredItems.map((article: any) => (
          <NewsCard
            key={article.id}
            article={article}
            lang={lang}
            onDismiss={() => dismissArticle(article.id)}
            onFavorite={() => toggleFavorite(article.id)}
            onReadingList={() => toggleReadingList(article.id)}
            isFavorite={favorites.has(article.id)}
            isInReadingList={readingList.has(article.id)}
          />
        ))}
      </div>
    </div>
  );
}
