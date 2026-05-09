"use client";
import { useState } from "react";
import { categoryLabel } from "@/lib/categories";

const CATEGORY_COLORS: Record<string, string> = {
  IA: "bg-purple-100 text-purple-800",
  DevOps: "bg-orange-100 text-orange-800",
  Cloud: "bg-blue-100 text-blue-800",
  "Sécurité": "bg-red-100 text-red-800",
  Dev: "bg-green-100 text-green-800",
  IT: "bg-gray-100 text-gray-800",
  Autre: "bg-yellow-100 text-yellow-800",
};

interface Props {
  article: any;
  lang?: "fr" | "en";
}

export default function NewsCard({ article, lang = "fr" }: Props) {
  const [expanded, setExpanded] = useState(false);
  const color = CATEGORY_COLORS[article.category] ?? CATEGORY_COLORS["Autre"];

  // Choisit la bonne version selon la langue, avec fallback sur les champs génériques
  const title = lang === "en"
    ? (article.title_en || article.title)
    : (article.title_fr || article.title);
  const shortDesc = lang === "en"
    ? (article.short_description_en || article.short_description)
    : (article.short_description_fr || article.short_description);
  const longDesc = lang === "en"
    ? (article.long_description_en || article.long_description)
    : (article.long_description_fr || article.long_description);

  return (
    <div
      style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
      className="rounded-lg border p-5 shadow-sm space-y-3 transition-colors"
    >
      <div
        className="flex items-start justify-between gap-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <h2 className="text-lg font-semibold leading-snug transition-colors"
          style={{ color: "var(--text)" }}>
          {title}
        </h2>
        <span className={`shrink-0 text-xs font-medium px-2 py-1 rounded-full ${color}`}>
          {categoryLabel(article.category, lang)}
        </span>
      </div>

      <p
        className="text-sm cursor-pointer transition-colors"
        style={{ color: "var(--text-muted)" }}
        onClick={() => setExpanded(!expanded)}
      >
        {shortDesc}
      </p>

      {expanded && longDesc && (
        <p className="text-sm pt-3 border-t"
          style={{ color: "var(--text)", borderColor: "var(--border)" }}>
          {longDesc}
        </p>
      )}

      <div className="flex items-center justify-between text-xs pt-1"
        style={{ color: "var(--text-muted)" }}>
        <div className="flex gap-3">
          <span>{article.source_name}</span>
          <span>·</span>
          <span>{new Date(article.published_at).toLocaleDateString("fr-FR")}</span>
        </div>
        <a
          href={article.article_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium hover:underline"
          style={{ color: "var(--accent)" }}
        >
          {lang === "en" ? "Read article →" : "Lire l'article →"}
        </a>
      </div>
    </div>
  );
}
