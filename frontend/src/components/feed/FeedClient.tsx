"use client";
/**
 * Partie interactive du feed. Les articles arrivent déjà filtrés et paginés
 * par le serveur (`app/page.tsx`) ; changer un filtre réécrit l'URL et
 * redemande un rendu serveur.
 *
 * Ce composant applique en plus les préférences d'articles locales
 * (`usePreferences`) : retrait immédiat d'un article supprimé ou marqué lu,
 * et, pour un visiteur anonyme, toutes ses préférences — le serveur ne
 * connaît pas encore son localStorage.
 */
import { useEffect, useRef, useState, useTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import useSWR from "swr";
import { useSession } from "next-auth/react";
import { chargerArticlesParIds } from "@/app/actions";
import { usePreferences, type RemotePrefs } from "@/lib/usePreferences";
import { writeDerniereVue } from "@/lib/feed-cookie";
import {
  composeFeed, correspondAuxPrefs, feedSearch, suggestions, vueMemorisee,
  type ArticlePrefs, type Columns, type FeedComposition, type FeedDefaults, type FeedQuery, type Lang,
} from "@/lib/feed";
import NewsCard from "@/components/NewsCard";
import SummaryLayer from "@/components/SummaryLayer";
import DropdownFilter from "@/components/DropdownFilter";
import RadioFilter from "@/components/RadioFilter";
import SearchBar from "@/components/SearchBar";
import TrashCard from "@/components/TrashCard";
import type { AppSession, Article, ArticleSummary } from "@/lib/types";

const COLUMN_CLASSES: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
};

interface Props {
  composition: FeedComposition;
  query: FeedQuery;
  defaults: FeedDefaults;
  /**
   * Préférences d'articles lues par le serveur (utilisateur connecté), dont
   * `composition` tient déjà compte ; null pour un visiteur anonyme.
   */
  prefsInitiales: RemotePrefs | null;
  isAdmin: boolean;
}

export default function FeedClient({ composition, query, defaults, prefsInitiales, isAdmin }: Props) {
  const prefsServeur = prefsInitiales !== null;
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();
  const { data: session } = useSession();
  const token = ((session as unknown) as AppSession | undefined)?.accessToken;

  const {
    favorites, readingList, readArticles,
    dismissedList, dismissedSet,
    toggleFavorite, addFavorite, toggleReadingList, toggleRead, dismiss, restoreArticle,
  } = usePreferences(prefsInitiales);

  // Dernier état demandé : évite qu'une 2e action rapide reparte de l'état
  // affiché alors que la navigation précédente n'est pas encore rendue.
  const demande = useRef<FeedQuery>(query);
  useEffect(() => { demande.current = query; }, [query]);

  // Colonnes : purement visuel, pas besoin d'un aller-retour serveur.
  const [columns, setColumns] = useState<Columns>(query.columns);
  useEffect(() => { setColumns(query.columns); }, [query.columns]);

  const [trashOpen, setTrashOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(query.terms.length > 0);

  const naviguer = (changes: Partial<FeedQuery>, { garderLimite = false, remplacer = false } = {}) => {
    const next: FeedQuery = { ...demande.current, columns, ...changes };
    if (!garderLimite) next.limit = next.pageSize;
    demande.current = next;
    writeDerniereVue(vueMemorisee(next, defaults));
    const href = pathname + feedSearch(next, defaults);
    startTransition(() => {
      if (remplacer) router.replace(href, { scroll: false });
      else router.push(href, { scroll: false });
    });
  };

  const changeColumns = (n: Columns) => {
    setColumns(n);
    demande.current = { ...demande.current, columns: n };
    writeDerniereVue(vueMemorisee(demande.current, defaults));
    // Next ≥ 14.1 synchronise history.replaceState avec le routeur, sans rendu serveur.
    window.history.replaceState(null, "", pathname + feedSearch(demande.current, defaults));
  };

  const changeLang = (lang: Lang) => naviguer({ lang }, { garderLimite: true });

  const toggleSource = (key: string) => {
    const courant = demande.current.excludedSources;
    const next = courant.includes(key) ? courant.filter((s) => s !== key) : [...courant, key];
    naviguer({ excludedSources: next });
  };

  const selectCategory = (category: string | null) => naviguer({ category });

  const setTerms = (terms: string[]) => naviguer({ terms });

  // ─── Favoris d'un visiteur anonyme : connus du seul navigateur ────────────
  const favorisClient = query.favorites && !prefsServeur;
  const favIds = favorisClient && favorites.size > 0 ? Array.from(favorites).sort().join(",") : null;
  const { data: favArticles, isLoading: favLoading } = useSWR<Article[]>(
    favIds ? ["favoris", favIds] : null,
    () => chargerArticlesParIds(favIds!.split(",")),
    { revalidateOnFocus: false }
  );
  const source: FeedComposition = favorisClient
    ? composeFeed([], favArticles ?? [], query, null)
    : composition;

  // ─── Préférences locales appliquées au rendu serveur ──────────────────────
  const localPrefs: ArticlePrefs = {
    favorites, readingList, read: readArticles, dismissed: dismissedSet,
  };
  const kept = source.items.filter((a) => correspondAuxPrefs(a, query, localPrefs));
  const total = source.total - (source.items.length - kept.length);
  const visibleItems = kept.slice(0, query.limit);
  const hasMore = total > visibleItems.length;
  const motsCles = prefsServeur ? source.suggestions : suggestions(kept, query.lang);

  // ─── Corbeille : articles chargés à la demande ────────────────────────────
  const corbeilleIds = trashOpen && dismissedList.length > 0 ? [...dismissedList].sort().join(",") : null;
  const { data: corbeille } = useSWR<Article[]>(
    corbeilleIds ? ["corbeille", corbeilleIds] : null,
    () => chargerArticlesParIds(corbeilleIds!.split(",")),
    { revalidateOnFocus: false, keepPreviousData: true }
  );
  const corbeilleItems = (corbeille ?? []).filter((a) => dismissedSet.has(a.id));

  // ─── Résumé IA (streaming SSE) ────────────────────────────────────────────
  const [summaryData, setSummaryData] = useState<ArticleSummary | null>(null);
  const [summaryArticleId, setSummaryArticleId] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryProgressMsg, setSummaryProgressMsg] = useState<string>("");
  const [summaryError, setSummaryError] = useState<string>("");

  const handleSummarize = async (article: { id: string }, force = false) => {
    if (!token) return;
    // Résumé déjà en cache local → ouvrir directement (sauf régénération forcée)
    if (!force && summaryData && summaryArticleId === article.id) {
      setSummaryOpen(true);
      return;
    }
    setSummaryOpen(false);
    setSummaryLoading(true);
    setSummaryProgressMsg("Initialisation…");
    setSummaryError("");
    // Invalide le cache local : summaryArticleId n'est reposé qu'à la réception
    // du résultat, sinon un échec laisserait summaryData (ancien article)
    // associé au nouvel id et rouvrirait le mauvais résumé.
    setSummaryArticleId(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/articles/${article.id}/summary${force ? "?force=true" : ""}`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok || !res.body) {
        throw new Error("Erreur lors de la génération du résumé.");
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          const event = JSON.parse(part.slice(6));
          if (event.type === "progress") {
            setSummaryProgressMsg(event.message);
          } else if (event.type === "result") {
            setSummaryData(event.data);
            setSummaryArticleId(article.id);
            setSummaryLoading(false);
            setSummaryProgressMsg("");
            setSummaryOpen(true);
            addFavorite(article.id);
          } else if (event.type === "error") {
            throw new Error(event.message || "Erreur lors de la génération du résumé.");
          }
        }
      }
    } catch (err: any) {
      setSummaryLoading(false);
      setSummaryProgressMsg("");
      setSummaryError(err.message || "Erreur lors de la génération du résumé.");
      setTimeout(() => setSummaryError(""), 5000);
    }
  };

  const lang = query.lang;
  const searchActive = searchOpen || query.terms.length > 0;

  const toggleStyle = (actif: boolean) => ({
    borderColor: actif ? "var(--accent)" : "var(--border)",
    backgroundColor: actif ? "var(--accent)" : "var(--surface)",
    color: actif ? "var(--bg)" : "var(--text-muted)",
  });

  return (
    <div className="space-y-4">
      {/* Toast résumé — non-bloquant, fixe en bas */}
      {(summaryLoading || summaryError) && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 px-5 py-3 rounded-full shadow-lg text-sm font-medium flex items-center gap-2"
          style={{
            backgroundColor: summaryError ? "#dc2626" : "var(--text)",
            color: summaryError ? "#fff" : "var(--bg)",
            maxWidth: "calc(100vw - 3rem)",
          }}
        >
          {summaryLoading && (
            <span className="shrink-0 animate-spin">⟳</span>
          )}
          <span className="truncate">
            {summaryLoading ? summaryProgressMsg : summaryError}
          </span>
        </div>
      )}

      {/* Layer résumé */}
      {summaryOpen && summaryData && (
        <SummaryLayer
          data={summaryData}
          initialLang={lang}
          onClose={() => setSummaryOpen(false)}
          onRegenerate={() => summaryArticleId && handleSummarize({ id: summaryArticleId }, true)}
        />
      )}

      {/* Ligne 1 : compteur + corbeille + contrôles */}
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
            {`${visibleItems.length} affiché${visibleItems.length > 1 ? "s" : ""} sur ${total}`}
          </span>
          {isPending && <span className="animate-spin" aria-label="Chargement">⟳</span>}
        </div>

        <div className="flex items-center gap-2">
          {/* Loupe */}
          <button
            onClick={() => {
              if (searchOpen && query.terms.length > 0) setTerms([]);
              setSearchOpen(o => !o);
            }}
            title={searchOpen ? "Fermer la recherche" : "Rechercher"}
            className="w-8 h-8 flex items-center justify-center rounded-md border transition text-sm"
            style={toggleStyle(searchActive)}
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
            {([1, 2, 3] as const).map((n) => (
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
          terms={query.terms}
          suggestions={motsCles}
          lang={lang}
          onAdd={(t) => setTerms([...demande.current.terms, t])}
          onRemove={(t) => setTerms(t === "__all__" ? [] : demande.current.terms.filter(x => x !== t))}
        />
      )}

      {/* Ligne 2 : filtres dropdown + favoris/lecture */}
      <div className="flex items-center gap-2 flex-wrap">
        <DropdownFilter
          label="Sources"
          items={composition.sources}
          excluded={new Set(query.excludedSources)}
          onToggle={toggleSource}
        />
        <RadioFilter
          label="Catégories"
          items={composition.categories}
          selected={query.category}
          onSelect={selectCategory}
          allLabel="Toutes"
        />
        <div className="flex gap-1 ml-1">
          <button
            onClick={() => naviguer({ favorites: !query.favorites })}
            title="Favoris"
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={toggleStyle(query.favorites)}
          >
            ⭐
          </button>
          <button
            onClick={() => naviguer({ readingList: !query.readingList })}
            title="Liste de lecture"
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={toggleStyle(query.readingList)}
          >
            👓
          </button>
          <button
            onClick={() => naviguer({ hideRead: !query.hideRead })}
            title={query.hideRead ? "Afficher les articles lus" : "Masquer les articles lus"}
            className="px-2.5 py-1.5 rounded-md border text-sm transition"
            style={toggleStyle(query.hideRead)}
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
            {corbeilleItems.map((article) => (
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
        <div className={`space-y-4 transition-opacity ${isPending ? "opacity-60" : ""}`}>
          {favorisClient && favLoading && <p style={{ color: "var(--text-muted)" }}>Chargement…</p>}
          {!(favorisClient && favLoading) && visibleItems.length === 0 && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Aucun article — ajuste les filtres ou réaffiche des sources.
            </p>
          )}
          <div className={`grid gap-4 ${COLUMN_CLASSES[columns]}`}>
            {visibleItems.map((article) => (
              <NewsCard
                key={article.id}
                article={article}
                lang={lang}
                onDismiss={() => dismiss(article.id)}
                onFavorite={() => toggleFavorite(article.id)}
                onReadingList={() => toggleReadingList(article.id)}
                onMarkRead={() => toggleRead(article.id)}
                onSummarize={() => handleSummarize(article)}
                isFavorite={favorites.has(article.id)}
                isInReadingList={readingList.has(article.id)}
                isRead={readArticles.has(article.id)}
                isAdmin={isAdmin}
              />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center pt-4">
              <button
                onClick={() => naviguer({ limit: demande.current.limit + query.pageSize }, { garderLimite: true, remplacer: true })}
                disabled={isPending}
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
        </div>
      )}
    </div>
  );
}
