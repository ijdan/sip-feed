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
    <div className="bg-white rounded-lg border p-5 shadow-sm space-y-3">
      <div
        className="flex items-start justify-between gap-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <h2 className="text-lg font-semibold leading-snug hover:text-blue-700 transition-colors">
          {title}
        </h2>
        <span className={`shrink-0 text-xs font-medium px-2 py-1 rounded-full ${color}`}>
          {categoryLabel(article.category, lang)}
        </span>
      </div>

      <p
        className="text-gray-600 text-sm cursor-pointer hover:text-gray-800 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {shortDesc}
      </p>

      {expanded && longDesc && (
        <p className="text-gray-700 text-sm border-t pt-3">{longDesc}</p>
      )}

      <div className="flex items-center justify-between text-xs text-gray-400 pt-1">
        <div className="flex gap-3">
          <span>{article.source_name}</span>
          <span>·</span>
          <span>{new Date(article.published_at).toLocaleDateString("fr-FR")}</span>
        </div>
        <a
          href={article.article_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 font-medium hover:underline"
        >
          {lang === "en" ? "Read article →" : "Lire l'article →"}
        </a>
      </div>
    </div>
  );
}
