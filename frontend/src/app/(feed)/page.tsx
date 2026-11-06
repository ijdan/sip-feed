/**
 * Page d'accueil — feed composé par le serveur de présentation.
 *
 * Le serveur lit l'état du feed dans l'URL, récupère articles, settings et
 * préférences auprès du backend, filtre et pagine, puis rend le HTML.
 * `FeedClient` ne garde que l'interactivité (menus, swipe, résumé IA) et
 * applique les actions faites depuis le dernier rendu.
 */
import { cookies } from "next/headers";
import FeedClient from "@/components/feed/FeedClient";
import { FEED_COOKIE, parseFeedCookie } from "@/lib/feed-cookie";
import {
  composeFeed, parseFeedQuery, resolveDefaults, toPrefs, type RawSearchParams,
} from "@/lib/feed";
import {
  articlesByIds, getServerAppSession, listArticles, userPreferences, userSettings,
} from "@/lib/server-api";

export default async function FeedPage({ searchParams }: { searchParams: RawSearchParams }) {
  const { token, isAdmin } = await getServerAppSession();

  const [articles, settings, remotePrefs] = await Promise.all([
    listArticles(token),
    userSettings(token),
    userPreferences(token),
  ]);

  const defaults = resolveDefaults(settings, parseFeedCookie(cookies().get(FEED_COOKIE)?.value));
  const query = parseFeedQuery(searchParams, defaults);
  const prefs = remotePrefs ? toPrefs(remotePrefs) : null;

  // Favoris : chargés par ids, sans restriction de rétention.
  // Sans préférences serveur (anonyme), le client s'en charge.
  const base = query.favorites && prefs
    ? await articlesByIds(Array.from(prefs.favorites), token)
    : articles;

  return (
    <FeedClient
      composition={composeFeed(articles, base, query, prefs)}
      query={query}
      defaults={defaults}
      prefsInitiales={remotePrefs}
      isAdmin={isAdmin}
    />
  );
}
