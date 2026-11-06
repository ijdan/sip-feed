"use server";
/**
 * Server Actions du feed. Le navigateur les appelle comme des fonctions ;
 * l'appel au backend est fait par le serveur de présentation.
 */
import { articlesByIds, getServerAppSession } from "@/lib/server-api";
import type { Article } from "@/lib/types";

const IDS_MAX = 1000;

/**
 * Charge des articles par identifiants, hors fenêtre de rétention.
 * Sert à la corbeille et aux favoris d'un visiteur anonyme, dont la liste
 * n'est connue que du navigateur (localStorage).
 */
export async function chargerArticlesParIds(ids: string[]): Promise<Article[]> {
  if (!Array.isArray(ids) || ids.length === 0) return [];
  const propres = ids.filter((id) => typeof id === "string" && id.length > 0).slice(0, IDS_MAX);
  const { token } = await getServerAppSession();
  return articlesByIds(propres, token);
}
