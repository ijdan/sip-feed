/**
 * Réglages utilisateur — type et valeurs par défaut.
 *
 * Module neutre (ni client ni serveur) : partagé par le hook `useSettings`
 * et par la composition serveur du feed (`lib/feed.ts`).
 */

export interface UserSettings {
  theme: "light" | "dark";
  columns: 1 | 2 | 3;
  font_size: "sm" | "md" | "lg";
  excluded_categories: string[];
  excluded_sources: string[];
  hide_read: boolean;
  default_lang: "fr" | "en";
  articles_per_page: 10 | 20 | 50 | 100;
}

export const DEFAULT_SETTINGS: UserSettings = {
  theme: "light",
  columns: 1,
  font_size: "md",
  excluded_categories: [],
  excluded_sources: [],
  hide_read: false,
  default_lang: "fr",
  articles_per_page: 20,
};
