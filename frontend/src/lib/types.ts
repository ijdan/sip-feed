/** Types partagés pour les données API et la session NextAuth. */

export interface AppSession {
  accessToken: string;
  role: "admin" | "reader";
  user?: { email?: string | null; name?: string | null };
}

export interface Article {
  id: string;
  title: string;
  title_fr: string;
  title_en: string;
  short_description: string;
  short_description_fr: string;
  short_description_en: string;
  long_description: string;
  long_description_fr: string;
  long_description_en: string;
  keywords_fr: string[];
  keywords_en: string[];
  article_url: string;
  source_name: string;
  source_id: string;
  category: string;
  published_at: string;
  collected_at: string;
}

export interface ArticleList {
  items: Article[];
}

/** Formate une date ISO en format long FR ou court selon le besoin. */
export function formatDate(isoDate: string, lang: "fr" | "en" = "fr", options?: Intl.DateTimeFormatOptions): string {
  const locale = lang === "en" ? "en-US" : "fr-FR";
  const defaultOptions: Intl.DateTimeFormatOptions = options ?? { day: "numeric", month: "short", year: "numeric" };
  return new Date(isoDate).toLocaleDateString(locale, defaultOptions);
}

export interface Source {
  id: string;
  name: string;
  type: "web" | "gmail";
  url?: string;
  gmail_sender?: string;
  active: boolean;
  created_by: string;
  created_at: string;
}
