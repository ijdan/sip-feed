"use client";
import { useState, useEffect } from "react";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import { usePreferences } from "@/lib/usePreferences";
import { useSettings } from "@/lib/useSettings";
import NewsCard from "@/components/NewsCard";
import DropdownFilter, { FilterItem } from "@/components/DropdownFilter";
import RadioFilter from "@/components/RadioFilter";
import SearchBar from "@/components/SearchBar";
import TrashCard from "@/components/TrashCard";
import { CATEGORIES, categoryLabel } from "@/lib/categories";

const COLUMN_CLASSES: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
};

export default function FeedPage() {
  const { data: session } = useSession();
  const token = ((session as unknown) as import("@/lib/types").AppSession)?.accessToken as string | undefined;
  const { settings, loaded } = useSettings();
  const [columns, setColumns] = useState<number>(1);
  const [lang, setLang] = useState<"fr" | "en">("fr"); // session uniquement, ne persiste pas
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const {
    favorites, readingList, readArticles,
    dismissedList, dismissedSet,
    toggleFavorite, toggleReadingList, toggleRead, dismiss, restoreArticle,
  } = usePreferences();
  const [trashOpen, setTrashOpen] = useState(false);
  const [filterFavorites, setFilterFavorites] = useState(false);
  const [filterReading, setFilterReading] = useState(false);
  const [hideRead, setHideRead] = useState(false);
  const [searchTerms, setSearchTerms] = useState<string[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const savedCols = localStorage.getItem("feed-columns");
    if (savedCols) setColumns(Number(savedCols));
    // La langue est initialisée depuis les settings (voir useEffect sur settings ci-dessous)
    const savedExcSrc = localStorage.getItem("feed-excluded-sources");
    if (savedExcSrc) setExcludedSources(new Set(JSON.parse(savedExcSrc)));
    const savedCat = localStorage.getItem("feed-selected-category");
    if (savedCat) setSelectedCategory(savedCat);
  }, []);

  // Appliquer les settings utilisateur quand ils sont chargés depuis Firestore
  useEffect(() => {
    if (!settings) return;
    setColumns(settings.columns);
    setExcludedSources(new Set(settings.excluded_sources));
    setHideRead(settings.hide_read ?? false);
    setLang(settings.default_lang as "fr" | "en" ?? "fr"); // langue par défaut depuis settings
  }, [settings]);

  const changeColumns = (n: number) => {
    setColumns(n);
    localStorage.setItem("feed-columns", String(n));
  };

  const changeLang = (l: "fr" | "en") => {
    setLang(l); // session uniquement — ne modifie pas settings.default_lang
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



  const apiBase = `${process.env.NEXT_PUBLIC_API_URL}/articles/`;
  const pageSize = settings.articles_per_page;

  // Y : nombre de "clics + 1" sur "Afficher plus" — la cible visible est pageSize × clicks
  const [clicks, setClicks] = useState(1);

  const { data, isLoading } = useSWR<{ items: any[] }>(
    loaded ? apiBase : null,
    (url: string) => fetch(url, token ? { headers: { Authorization: `Bearer ${token}` } } : {})
      .then(r => r.json()),
    { revalidateOnFocus: false }
  );

  const allItems: any[] = data?.items ?? [];
  const targetVisible = pageSize * clicks;

  // Sources uniques avec compteurs (sur les articles chargés)
  const sourceCountsAll: Record<string, number> = allItems.reduce(
    (acc: Record<string, number>, a: any) => {
      acc[a.source_name] = (acc[a.source_name] ?? 0) + 1;
      return acc;
    }, {}
  );
  const sourceItems: FilterItem[] = Object.entries(sourceCountsAll)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, count]) => ({ key, label: key, count }));

  // Catégories avec compteurs (sur les articles chargés)
  const categoryItems: FilterItem[] = CATEGORIES.map((cat) => ({
    key: cat,
    label: categoryLabel(cat, lang),
    count: allItems.filter((a: any) => a.category === cat).length,
  }));

  // Articles filtrés côté client — uniquement les filtres sans équivalent backend.
  // Les articles dismissés et les sources exclues sont déjà filtrés par le backend ;
  // on les garde ici en filet de sécurité pour les réponses mises en cache (stale).
  const filteredItems = allItems.filter((a: any) => {
    if (dismissedSet.has(a.id)) return false;
    if (excludedSources.has(a.source_name)) return false;
    if (selectedCategory !== null && a.category !== selectedCategory) return false;
    if (filterFavorites && !favorites.has(a.id)) return false;
    if (filterReading && !readingList.has(a.id)) return false;
    if (hideRead && readArticles.has(a.id)) return false;
    if (searchTerms.length > 0) {
      const kw = ((lang === "en" ? a.keywords_en : a.keywords_fr) ?? [])
        .map((k: string) => k.toLowerCase());
      if (!searchTerms.every(t => kw.some(k => k.includes(t.toLowerCase())))) return false;
    }
    return true;
  });

  // Articles réellement affichés : on slice à pageSize × clicks
  const visibleItems = filteredItems.slice(0, targetVisible);
  const hasMore = filteredItems.length > visibleItems.length;

  // Reset clicks à 1 quand un filtre change.
  // dismissedSet est volontairement exclu : c'est une action item-level, pas un filtre global.
  useEffect(() => {
    setClicks(1);
  }, [excludedSources, selectedCategory, filterFavorites, filterReading, hideRead, searchTerms]);

  useEffect(() => {
    setClicks(1);
  }, [pageSize]);

  // Suggestions contextuelles : mots-clés des articles déjà filtrés
  // → se réduisent au fur et à mesure des mots-clés sélectionnés
  const allKeywords: string[] = Array.from(
    new Set<string>(filteredItems.flatMap((a: any) =>
      lang === "en" ? (a.keywords_en ?? []) : (a.keywords_fr ?? [])
    ))
  ).sort();

  return (
    <div className="space-y-4">

      {/* Ligne 1 : compteur + undo + contrôles */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <button
            onClick={() => setTrashOpen(o => !o)}
            title={dismissedList.length > 0
              ? `Corbeille (${dismissedList.length} article${dismissedList.length > 1 ? "s" : ""})`
              : "Corbeille vide"}
            className="flex items-center gap-1 px-2 py-1 rounded-md border text-sm transition"
            style={{
              borderColor: trashOpen ? "var(--accent)" : "var(--border)",
              backgroundColor: trashOpen ? "var(--accent)" : "var(--surface)",
              color: trashOpen ? "var(--bg)" : dismissedList.length > 0 ? "var(--text)" : "var(--text-muted)",
              opacity: dismissedList.length === 0 && !trashOpen ? 0.5 : 1,
            }}
          >
            🗑️
          </button>
          <span>
            {isLoading ? "…" : `${visibleItems.length} affiché${visibleItems.length > 1 ? "s" : ""} sur ${filteredItems.length}`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Loupe */}
          <button
            onClick={() => { setSearchOpen(o => !o); if (searchOpen) setSearchTerms([]); }}
            title={searchOpen ? "Fermer la recherche" : "Rechercher"}
            className="w-8 h-8 flex items-center justify-center rounded-md border transition text-sm"
            style={{
              borderColor: searchOpen || searchTerms.length > 0 ? "var(--accent)" : "var(--border)",
              backgroundColor: searchOpen || searchTerms.length > 0 ? "var(--accent)" : "var(--surface)",
              color: searchOpen || searchTerms.length > 0 ? "var(--bg)" : "var(--text-muted)",
            }}
          >🔍</button>

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

      {/* Barre de recherche — visible uniquement si ouverte */}
      {searchOpen && (
        <SearchBar
          terms={searchTerms}
          suggestions={allKeywords}
          lang={lang}
          onAdd={(t) => setSearchTerms(prev => [...prev, t])}
          onRemove={(t) => {
            if (t === "__all__") setSearchTerms([]);
            else setSearchTerms(prev => prev.filter(x => x !== t));
          }}
        />
      )}

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
            title="Favoris"
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={{
              borderColor: filterFavorites ? "var(--accent)" : "var(--border)",
              backgroundColor: filterFavorites ? "var(--accent)" : "var(--surface)",
              color: filterFavorites ? "var(--bg)" : "var(--text-muted)",
            }}
          >
            ⭐
          </button>
          <button
            onClick={() => setFilterReading(r => !r)}
            title="Liste de lecture"
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={{
              borderColor: filterReading ? "var(--accent)" : "var(--border)",
              backgroundColor: filterReading ? "var(--accent)" : "var(--surface)",
              color: filterReading ? "var(--bg)" : "var(--text-muted)",
            }}
          >
            👓
          </button>
          <button
            onClick={() => setHideRead(h => !h)}
            title={hideRead ? "Afficher les articles lus" : "Masquer les articles lus"}
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={{
              borderColor: hideRead ? "var(--accent)" : "var(--border)",
              backgroundColor: hideRead ? "var(--accent)" : "var(--surface)",
              color: hideRead ? "var(--bg)" : "var(--text-muted)",
            }}
          >
            ✓
          </button>
        </div>
      </div>

      {/* Feed */}
      {trashOpen ? (
        /* Vue corbeille */
        <div className="space-y-3">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {dismissedList.length} article{dismissedList.length > 1 ? "s" : ""} supprimé{dismissedList.length > 1 ? "s" : ""} — balayez droite→gauche pour restaurer.
          </p>
          {dismissedList.length === 0 && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>La corbeille est vide.</p>
          )}
          <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
            {[...dismissedList]
              .map(id => allItems.find((a: any) => a.id === id))
              .filter(Boolean)
              .sort((a: any, b: any) => b.published_at.localeCompare(a.published_at))
              .map((article: any) => (
                <TrashCard
                  key={article.id}
                  article={article}
                  lang={lang}
                  onRestore={() => restoreArticle(article.id)}
                />
              ))}
          </div>
        </div>
      ) : (
        /* Vue feed normale */
        <>
          {isLoading && <p style={{ color: "var(--text-muted)" }}>Chargement…</p>}
          {!isLoading && visibleItems.length === 0 && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Aucun article — ajuste les filtres ou réaffiche des sources.
            </p>
          )}
          <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
            {visibleItems.map((article: any) => (
              <NewsCard
                key={article.id}
                article={article}
                lang={lang}
                onDismiss={() => dismiss(article.id)}
                onFavorite={() => toggleFavorite(article.id)}
                onReadingList={() => toggleReadingList(article.id)}
                onMarkRead={() => toggleRead(article.id)}
                isFavorite={favorites.has(article.id)}
                isInReadingList={readingList.has(article.id)}
                isRead={readArticles.has(article.id)}
              />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center pt-4">
              <button
                onClick={() => setClicks(c => c + 1)}
                className="px-4 py-2 rounded-md border text-sm transition"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "var(--surface)",
                  color: "var(--text)",
                }}
              >
                Afficher plus
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
