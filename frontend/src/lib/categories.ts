export const CATEGORY_LABELS: Record<string, { fr: string; en: string }> = {
  IA:        { fr: "IA",       en: "AI" },
  DevOps:    { fr: "DevOps",   en: "DevOps" },
  Cloud:     { fr: "Cloud",    en: "Cloud" },
  Sécurité:  { fr: "Sécurité", en: "Security" },
  Dev:       { fr: "Dev",      en: "Dev" },
  IT:        { fr: "IT",       en: "IT" },
  Autre:     { fr: "Autre",    en: "Other" },
};

export const CATEGORIES = Object.keys(CATEGORY_LABELS);

export function categoryLabel(cat: string, lang: "fr" | "en"): string {
  return CATEGORY_LABELS[cat]?.[lang] ?? cat;
}
