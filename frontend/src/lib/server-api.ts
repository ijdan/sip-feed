/**
 * Accès au backend depuis le serveur de présentation (Server Components,
 * Server Actions). Ne doit jamais être importé par un composant client.
 *
 * - URL du backend lue à l'exécution (`BACKEND_URL`), avec repli sur
 *   `NEXT_PUBLIC_API_URL` (inliné au build) pour ne rien casser en local.
 * - Le JWT applicatif est lu dans la session NextAuth côté serveur.
 * - Pour un visiteur anonyme, l'en-tête `X-Forwarded-For` du navigateur est
 *   relayé : `StatsMiddleware` du backend continue ainsi de compter les
 *   appels par visiteur, et non par instance du frontend.
 */
import "server-only";
import { headers } from "next/headers";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import type { AppSession, Article, ArticleList } from "@/lib/types";
import type { UserSettings } from "@/lib/settings-defaults";

export interface UserPreferences {
  favorites: string[];
  reading_list: string[];
  read_articles: string[];
  dismissed: string[];
}

export interface ServerAppSession {
  token?: string;
  isAdmin: boolean;
}

/** Nombre max d'identifiants acceptés par `GET /articles/?ids=` (cf. backend). */
const IDS_PAR_APPEL = 200;

export class BackendError extends Error {
  constructor(public status: number, path: string) {
    super(`Backend ${status} sur ${path}`);
  }
}

function backendUrl(): string {
  const url = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error("BACKEND_URL (ou NEXT_PUBLIC_API_URL) n'est pas défini");
  return url.replace(/\/$/, "");
}

export async function getServerAppSession(): Promise<ServerAppSession> {
  const session = (await getServerSession(authOptions)) as unknown as AppSession | null;
  return {
    token: session?.accessToken || undefined,
    isAdmin: session?.role === "admin",
  };
}

async function backendGet<T>(path: string, token?: string): Promise<T> {
  const h: Record<string, string> = {};
  if (token) {
    h.Authorization = `Bearer ${token}`;
  } else {
    const xff = headers().get("x-forwarded-for");
    if (xff) h["X-Forwarded-For"] = xff;
  }
  // no-store : le feed doit refléter la dernière collecte, et chaque affichage
  // doit être compté par StatsMiddleware comme avant.
  const res = await fetch(`${backendUrl()}${path}`, { headers: h, cache: "no-store" });
  if (!res.ok) throw new BackendError(res.status, path);
  return res.json() as Promise<T>;
}

/** Articles de la fenêtre de rétention, du plus récent au plus ancien. */
export async function listArticles(token?: string): Promise<Article[]> {
  const data = await backendGet<ArticleList>("/articles/", token);
  return data.items ?? [];
}

/** Articles par identifiants, sans filtre de rétention (favoris, corbeille). */
export async function articlesByIds(ids: string[], token?: string): Promise<Article[]> {
  const uniques = Array.from(new Set(ids.filter(Boolean)));
  const lots: string[][] = [];
  for (let i = 0; i < uniques.length; i += IDS_PAR_APPEL) {
    lots.push(uniques.slice(i, i + IDS_PAR_APPEL));
  }
  const resultats = await Promise.all(
    lots.map((lot) =>
      backendGet<ArticleList>(`/articles/?ids=${encodeURIComponent(lot.join(","))}`, token)
    )
  );
  return resultats
    .flatMap((r) => r.items ?? [])
    .sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
}

/** Settings de l'utilisateur connecté, ou null (anonyme, token expiré, backend KO). */
export async function userSettings(token?: string): Promise<UserSettings | null> {
  if (!token) return null;
  try {
    return await backendGet<UserSettings>("/users/me/settings", token);
  } catch {
    return null;
  }
}

/** Préférences (favoris, lecture, lus, corbeille) de l'utilisateur connecté, ou null. */
export async function userPreferences(token?: string): Promise<UserPreferences | null> {
  if (!token) return null;
  try {
    return await backendGet<UserPreferences>("/users/me/preferences", token);
  } catch {
    return null;
  }
}
