"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";

interface RemotePrefs {
  favorites: string[];
  reading_list: string[];
  read_articles: string[];
  dismissed: string[];
}

const API = process.env.NEXT_PUBLIC_API_URL;

async function fetchRemote(token: string): Promise<RemotePrefs | null> {
  try {
    const res = await fetch(`${API}/users/me/preferences`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok ? res.json() : null;
  } catch { return null; }
}

async function pushRemote(token: string, prefs: RemotePrefs): Promise<void> {
  try {
    await fetch(`${API}/users/me/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(prefs),
    });
  } catch { /* silent fail — localStorage reste le fallback */ }
}

function loadLocal() {
  if (typeof window === "undefined") return null;
  return {
    favorites: new Set<string>(JSON.parse(localStorage.getItem("feed-favorites") ?? "[]")),
    readingList: new Set<string>(JSON.parse(localStorage.getItem("feed-reading-list") ?? "[]")),
    readArticles: new Set<string>(JSON.parse(localStorage.getItem("feed-read-articles") ?? "[]")),
    dismissed: JSON.parse(localStorage.getItem("feed-dismissed") ?? "[]") as string[],
  };
}

function saveLocal(
  favorites: Set<string>, readingList: Set<string>,
  readArticles: Set<string>, dismissed: string[]
) {
  localStorage.setItem("feed-favorites", JSON.stringify(Array.from(favorites)));
  localStorage.setItem("feed-reading-list", JSON.stringify(Array.from(readingList)));
  localStorage.setItem("feed-read-articles", JSON.stringify(Array.from(readArticles)));
  localStorage.setItem("feed-dismissed", JSON.stringify(dismissed));
}

export function usePreferences() {
  const { data: session } = useSession();
  const token = ((session as unknown) as import("@/lib/types").AppSession)?.accessToken as string | undefined;

  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [readingList, setReadingList] = useState<Set<string>>(new Set());
  const [readArticles, setReadArticles] = useState<Set<string>>(new Set());
  const [dismissedList, setDismissedList] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Ref pour avoir toujours les valeurs à jour dans les callbacks
  const state = useRef({ favorites, readingList, readArticles, dismissedList });
  useEffect(() => { state.current = { favorites, readingList, readArticles, dismissedList }; });

  // Chargement initial : localStorage puis merge Firestore
  useEffect(() => {
    const local = loadLocal();
    if (local) {
      setFavorites(local.favorites);
      setReadingList(local.readingList);
      setReadArticles(local.readArticles);
      setDismissedList(local.dismissed);
    }
    setLoaded(true);

    if (token) {
      fetchRemote(token).then((remote) => {
        if (!remote) return;
        // Merge : union des deux sources (union = on garde tout)
        const merged = {
          favorites: new Set<string>([...Array.from(local?.favorites ?? new Set<string>()), ...remote.favorites]),
          readingList: new Set<string>([...Array.from(local?.readingList ?? new Set<string>()), ...remote.reading_list]),
          readArticles: new Set<string>([...Array.from(local?.readArticles ?? new Set<string>()), ...remote.read_articles]),
          dismissed: Array.from(new Set([...(local?.dismissed ?? []), ...remote.dismissed])),
        };
        setFavorites(merged.favorites);
        setReadingList(merged.readingList);
        setReadArticles(merged.readArticles);
        setDismissedList(merged.dismissed);
        saveLocal(merged.favorites, merged.readingList, merged.readArticles, merged.dismissed);
        // Sync le merge vers Firestore
        pushRemote(token, {
          favorites: Array.from(merged.favorites),
          reading_list: Array.from(merged.readingList),
          read_articles: Array.from(merged.readArticles),
          dismissed: merged.dismissed,
        });
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const persist = useCallback((
    fav: Set<string>, rl: Set<string>, ra: Set<string>, dis: string[]
  ) => {
    saveLocal(fav, rl, ra, dis);
    if (token) {
      pushRemote(token, {
        favorites: Array.from(fav),
        reading_list: Array.from(rl),
        read_articles: Array.from(ra),
        dismissed: dis,
      });
    }
  }, [token]);

  const toggleFavorite = useCallback((id: string) => {
    const next = new Set(state.current.favorites);
    next.has(id) ? next.delete(id) : next.add(id);
    setFavorites(next);
    persist(next, state.current.readingList, state.current.readArticles, state.current.dismissedList);
  }, [persist]);

  const toggleReadingList = useCallback((id: string) => {
    const next = new Set(state.current.readingList);
    next.has(id) ? next.delete(id) : next.add(id);
    setReadingList(next);
    persist(state.current.favorites, next, state.current.readArticles, state.current.dismissedList);
  }, [persist]);

  const toggleRead = useCallback((id: string) => {
    const next = new Set(state.current.readArticles);
    next.has(id) ? next.delete(id) : next.add(id);
    setReadArticles(next);
    persist(state.current.favorites, state.current.readingList, next, state.current.dismissedList);
  }, [persist]);

  const dismiss = useCallback((id: string) => {
    if (state.current.dismissedList.includes(id)) return;
    const nextDis = [...state.current.dismissedList, id];
    const nextFav = new Set(state.current.favorites); nextFav.delete(id);
    const nextRL = new Set(state.current.readingList); nextRL.delete(id);
    setDismissedList(nextDis);
    setFavorites(nextFav);
    setReadingList(nextRL);
    persist(nextFav, nextRL, state.current.readArticles, nextDis);
  }, [persist]);

  const undoDismiss = useCallback(() => {
    const next = state.current.dismissedList.slice(0, -1);
    setDismissedList(next);
    persist(state.current.favorites, state.current.readingList, state.current.readArticles, next);
  }, [persist]);

  const restoreArticle = useCallback((id: string) => {
    const next = state.current.dismissedList.filter(x => x !== id);
    setDismissedList(next);
    persist(state.current.favorites, state.current.readingList, state.current.readArticles, next);
  }, [persist]);

  return {
    favorites, readingList, readArticles,
    dismissedList, dismissedSet: new Set(dismissedList),
    toggleFavorite, toggleReadingList, toggleRead, dismiss, undoDismiss, restoreArticle,
    loaded,
  };
}
