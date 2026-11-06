/**
 * Composition du feed — fonctions pures, sans accès réseau ni DOM.
 *
 * Exécutées par le serveur de présentation (`app/page.tsx`) pour produire la
 * page déjà filtrée, et réutilisées par le client pour appliquer les actions
 * faites depuis le dernier rendu serveur (article supprimé, marqué lu…).
 *
 * L'état du feed vit dans l'URL : `?cat=IA&exclus=TLDR&q=rust&n=40&lang=en…`.
 * Un paramètre absent prend la valeur par défaut de l'utilisateur
 * (settings serveur s'il est connecté, sinon cookie `sip-feed-vue`, sinon
 * DEFAULT_SETTINGS). Ces défauts ne changent qu'en modifiant ses settings :
 * seules les valeurs qui en diffèrent sont écrites dans l'URL, d'où une valeur
 * vide explicite (`exclus=`) pour « aucune source exclue » quand le défaut en a.
 */
import { CATEGORIES, categoryLabel } from "@/lib/categories";
import { DEFAULT_SETTINGS, type UserSettings } from "@/lib/settings-defaults";
import type { FeedCookie } from "@/lib/feed-cookie";
import type { Article } from "@/lib/types";
import type { FilterItem } from "@/components/DropdownFilter";

export type Lang = "fr" | "en";
export type Columns = 1 | 2 | 3;
export type RawSearchParams = Record<string, string | string[] | undefined>;

/** Noms des paramètres d'URL du feed. */
export const PARAM = {
  lang: "lang",
  cols: "cols",
  cat: "cat",
  exclus: "exclus",
  q: "q",
  favoris: "favoris",
  lecture: "lecture",
  masquerLus: "masquer_lus",
  n: "n",
} as const;

const PAGE_SIZES = [10, 20, 50, 100];
const LIMIT_MAX = 1000;
/** Articles envoyés au-delà de la page visible, pour combler les retraits faits côté client. */
export const TAMPON_ARTICLES = 20;

export interface FeedDefaults {
  lang: Lang;
  columns: Columns;
  excludedSources: string[];
  hideRead: boolean;
  pageSize: number;
}

export interface FeedQuery extends FeedDefaults {
  category: string | null;
  terms: string[];
  favorites: boolean;
  readingList: boolean;
  /** Nombre d'articles visibles (pageSize × clics sur « Afficher plus »). */
  limit: number;
}

/** Préférences d'articles (favoris, lecture, lus, corbeille). */
export interface ArticlePrefs {
  favorites: Set<string>;
  readingList: Set<string>;
  read: Set<string>;
  dismissed: Set<string>;
}

export interface FeedComposition {
  /** Articles filtrés, tronqués à `limit + TAMPON_ARTICLES` quand les préférences sont connues. */
  items: Article[];
  /** Nombre total d'articles correspondant aux filtres. */
  total: number;
  sources: FilterItem[];
  categories: FilterItem[];
  suggestions: string[];
}

// ─── Paramètres d'URL ────────────────────────────────────────────────────────

const isLang = (v: unknown): v is Lang => v === "fr" || v === "en";
const isColumns = (v: unknown): v is Columns => v === 1 || v === 2 || v === 3;
const isCategory = (v: unknown): v is string => typeof v === "string" && CATEGORIES.includes(v);

function premier(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

/** `undefined` si absent, sinon la liste des valeurs non vides (`exclus=` → []). */
function liste(v: string | string[] | undefined): string[] | undefined {
  if (v === undefined) return undefined;
  return (Array.isArray(v) ? v : [v]).filter((s) => s !== "");
}

function booleen(v: string | string[] | undefined): boolean | undefined {
  const s = premier(v);
  if (s === undefined) return undefined;
  return s === "1";
}

/** Valeurs par défaut : settings serveur > cookie > DEFAULT_SETTINGS. */
export function resolveDefaults(settings: UserSettings | null, cookie: FeedCookie): FeedDefaults {
  const s: Partial<UserSettings> = settings ?? {};
  const columns = Number(s.columns ?? cookie.columns);
  const pageSize = Number(s.articles_per_page ?? cookie.articles_per_page);
  const lang = s.default_lang ?? cookie.default_lang;
  return {
    lang: isLang(lang) ? lang : DEFAULT_SETTINGS.default_lang,
    columns: isColumns(columns) ? columns : DEFAULT_SETTINGS.columns,
    excludedSources: s.excluded_sources ?? cookie.excluded_sources ?? DEFAULT_SETTINGS.excluded_sources,
    hideRead: s.hide_read ?? cookie.hide_read ?? DEFAULT_SETTINGS.hide_read,
    pageSize: PAGE_SIZES.includes(pageSize) ? pageSize : DEFAULT_SETTINGS.articles_per_page,
  };
}

export function parseFeedQuery(sp: RawSearchParams, d: FeedDefaults): FeedQuery {
  const lang = premier(sp[PARAM.lang]);
  const cols = Number(premier(sp[PARAM.cols]));
  const cat = premier(sp[PARAM.cat]);
  const n = parseInt(premier(sp[PARAM.n]) ?? "", 10);
  return {
    lang: isLang(lang) ? lang : d.lang,
    columns: isColumns(cols) ? cols : d.columns,
    category: isCategory(cat) ? cat : null,
    excludedSources: liste(sp[PARAM.exclus]) ?? d.excludedSources,
    hideRead: booleen(sp[PARAM.masquerLus]) ?? d.hideRead,
    pageSize: d.pageSize,
    terms: liste(sp[PARAM.q]) ?? [],
    favorites: booleen(sp[PARAM.favoris]) ?? false,
    readingList: booleen(sp[PARAM.lecture]) ?? false,
    limit: Number.isFinite(n) ? Math.min(Math.max(n, d.pageSize), LIMIT_MAX) : d.pageSize,
  };
}

const memeListe = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

/** Sérialise l'état du feed en query string, en omettant les valeurs par défaut. */
export function feedSearch(q: FeedQuery, d: FeedDefaults): string {
  const p = new URLSearchParams();
  if (q.lang !== d.lang) p.set(PARAM.lang, q.lang);
  if (q.columns !== d.columns) p.set(PARAM.cols, String(q.columns));
  if (q.category) p.set(PARAM.cat, q.category);
  if (!memeListe(q.excludedSources, d.excludedSources)) {
    if (q.excludedSources.length === 0) p.set(PARAM.exclus, "");
    else q.excludedSources.forEach((s) => p.append(PARAM.exclus, s));
  }
  q.terms.forEach((t) => p.append(PARAM.q, t));
  if (q.favorites) p.set(PARAM.favoris, "1");
  if (q.readingList) p.set(PARAM.lecture, "1");
  if (q.hideRead !== d.hideRead) p.set(PARAM.masquerLus, q.hideRead ? "1" : "0");
  if (q.limit !== q.pageSize) p.set(PARAM.n, String(q.limit));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Partie de la vue mémorisée d'une visite à l'autre : catégorie, sources, colonnes. */
export function vueMemorisee(q: FeedQuery, d: FeedDefaults): string {
  return feedSearch({
    ...d,
    category: q.category,
    excludedSources: q.excludedSources,
    columns: q.columns,
    terms: [],
    favorites: false,
    readingList: false,
    limit: d.pageSize,
  }, d);
}

// ─── Filtrage ────────────────────────────────────────────────────────────────

export function keywords(a: Article, lang: Lang): string[] {
  return (lang === "en" ? a.keywords_en : a.keywords_fr) ?? [];
}

/** Filtres portés par l'URL (indépendants des préférences d'articles). */
function correspondAuxFiltres(a: Article, q: FeedQuery): boolean {
  if (q.excludedSources.includes(a.source_name)) return false;
  if (q.category !== null && a.category !== q.category) return false;
  if (q.terms.length > 0) {
    const kw = keywords(a, q.lang).map((k) => k.toLowerCase());
    if (!q.terms.every((t) => kw.some((k) => k.includes(t.toLowerCase())))) return false;
  }
  return true;
}

/** Filtres qui dépendent des préférences d'articles de l'utilisateur. */
export function correspondAuxPrefs(a: Article, q: FeedQuery, prefs: ArticlePrefs): boolean {
  if (prefs.dismissed.has(a.id)) return false;
  if (q.favorites && !prefs.favorites.has(a.id)) return false;
  if (q.readingList && !prefs.readingList.has(a.id)) return false;
  if (q.hideRead && prefs.read.has(a.id)) return false;
  return true;
}

export function toPrefs(p: {
  favorites?: Iterable<string>;
  reading_list?: Iterable<string>;
  read_articles?: Iterable<string>;
  dismissed?: Iterable<string>;
}): ArticlePrefs {
  return {
    favorites: new Set(p.favorites ?? []),
    readingList: new Set(p.reading_list ?? []),
    read: new Set(p.read_articles ?? []),
    dismissed: new Set(p.dismissed ?? []),
  };
}

/** Mots-clés proposés par la recherche : ceux des articles déjà filtrés. */
export function suggestions(items: Article[], lang: Lang): string[] {
  return Array.from(new Set(items.flatMap((a) => keywords(a, lang)))).sort();
}

/**
 * Compose le feed.
 *
 * @param articles  articles de la fenêtre de rétention (base des compteurs de filtres)
 * @param base      articles à filtrer — `articles`, ou les favoris chargés par ids
 * @param prefs     préférences connues du serveur ; `null` pour un visiteur anonyme,
 *                  auquel cas la liste complète est renvoyée et le client applique
 *                  ses préférences locales.
 */
export function composeFeed(
  articles: Article[],
  base: Article[],
  q: FeedQuery,
  prefs: ArticlePrefs | null,
): FeedComposition {
  const filtered = base.filter(
    (a) => correspondAuxFiltres(a, q) && (prefs === null || correspondAuxPrefs(a, q, prefs))
  );

  const parSource = articles.reduce<Record<string, number>>((acc, a) => {
    acc[a.source_name] = (acc[a.source_name] ?? 0) + 1;
    return acc;
  }, {});

  return {
    items: prefs === null ? filtered : filtered.slice(0, q.limit + TAMPON_ARTICLES),
    total: filtered.length,
    sources: Object.entries(parSource)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, count]) => ({ key, label: key, count })),
    categories: CATEGORIES.map((cat) => ({
      key: cat,
      label: categoryLabel(cat, q.lang),
      count: articles.filter((a) => a.category === cat).length,
    })),
    suggestions: suggestions(filtered, q.lang),
  };
}
