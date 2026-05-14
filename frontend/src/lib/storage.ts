/** Clés localStorage centralisées — évite les typos et facilite les refactorings. */
export const STORAGE_KEYS = {
  FEED_COLUMNS:            "feed-columns",
  FEED_LANG:               "feed-lang",
  FEED_EXCLUDED_SOURCES:   "feed-excluded-sources",
  FEED_SELECTED_CATEGORY:  "feed-selected-category",
  FEED_DISMISSED:          "feed-dismissed",
  FEED_FAVORITES:          "feed-favorites",
  FEED_READING_LIST:       "feed-reading-list",
  FEED_READ_ARTICLES:      "feed-read-articles",
  FEED_HIDE_READ:          "feed-hide-read",
  USER_SETTINGS:           "user-settings",
  SETTINGS_DEFAULT_LANG:   "settings-default-lang",
} as const;

export type StorageKey = typeof STORAGE_KEYS[keyof typeof STORAGE_KEYS];
