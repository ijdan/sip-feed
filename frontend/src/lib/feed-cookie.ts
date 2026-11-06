/**
 * Cookies lus par le serveur de présentation, qui n'a pas accès au localStorage.
 *
 * - `sip-feed-vue` : miroir des settings utiles au rendu du feed (colonnes,
 *   sources exclues, langue, taille de page…). Écrit par `useSettings` ;
 *   sert de valeurs par défaut aux visiteurs anonymes.
 * - `sip-feed-derniere-vue` : query string de la dernière vue du feed
 *   (catégorie, sources, colonnes). Écrit par le feed ; quand on arrive sur `/`
 *   sans paramètre, le serveur redirige vers cette vue.
 */

export const FEED_COOKIE = "sip-feed-vue";
export const DERNIERE_VUE_COOKIE = "sip-feed-derniere-vue";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

export interface FeedCookie {
  columns?: 1 | 2 | 3;
  excluded_sources?: string[];
  hide_read?: boolean;
  default_lang?: "fr" | "en";
  articles_per_page?: number;
}

/** Parse la valeur brute du cookie — tolère une valeur absente ou corrompue. */
export function parseFeedCookie(raw: string | undefined | null): FeedCookie {
  if (!raw) return {};
  // Selon le lecteur, la valeur arrive déjà décodée (cookies() de Next) ou non (document.cookie).
  for (const candidat of [raw, safeDecode(raw)]) {
    try {
      const parsed = JSON.parse(candidat);
      if (parsed && typeof parsed === "object") return parsed;
    } catch { /* candidat suivant */ }
  }
  return {};
}

function safeDecode(s: string): string {
  try { return decodeURIComponent(s); } catch { return s; }
}

function readClientCookie(): FeedCookie {
  if (typeof document === "undefined") return {};
  const entry = document.cookie.split("; ").find((c) => c.startsWith(`${FEED_COOKIE}=`));
  return parseFeedCookie(entry?.slice(FEED_COOKIE.length + 1));
}

function ecrire(nom: string, valeur: string): void {
  document.cookie = `${nom}=${valeur}; path=/; max-age=${MAX_AGE_SECONDS}; samesite=lax`;
}

/** Fusionne `partial` dans le cookie (côté navigateur uniquement). */
export function writeFeedCookie(partial: FeedCookie): void {
  if (typeof document === "undefined") return;
  const next = { ...readClientCookie(), ...partial };
  ecrire(FEED_COOKIE, encodeURIComponent(JSON.stringify(next)));
}

/** Mémorise la dernière vue du feed (query string sans `?`, vide = vue par défaut). */
export function writeDerniereVue(search: string): void {
  if (typeof document === "undefined") return;
  ecrire(DERNIERE_VUE_COOKIE, encodeURIComponent(search.replace(/^\?/, "")));
}
