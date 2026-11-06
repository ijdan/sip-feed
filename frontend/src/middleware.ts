/**
 * Arrivée sur `/` sans paramètre : redirection vers la dernière vue du feed
 * (catégorie, sources, colonnes), mémorisée par le cookie `sip-feed-derniere-vue`.
 * Fait ici plutôt que dans la page pour renvoyer une vraie 307 avant tout rendu.
 */
import { NextRequest, NextResponse } from "next/server";
import { DERNIERE_VUE_COOKIE } from "@/lib/feed-cookie";

export function middleware(req: NextRequest) {
  if (req.nextUrl.search) return NextResponse.next();
  // La valeur est déjà décodée : c'est la query string d'origine.
  const derniereVue = req.cookies.get(DERNIERE_VUE_COOKIE)?.value;
  if (!derniereVue) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.search = `?${derniereVue}`;
  return NextResponse.redirect(url);
}

export const config = { matcher: "/" };
