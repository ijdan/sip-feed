"use client";
import { useState } from "react";

const CATEGORY_COLORS: Record<string, string> = {
  IA: "bg-purple-100 text-purple-800",
  DevOps: "bg-orange-100 text-orange-800",
  Cloud: "bg-blue-100 text-blue-800",
  "Sécurité": "bg-red-100 text-red-800",
  Dev: "bg-green-100 text-green-800",
  IT: "bg-gray-100 text-gray-800",
  Autre: "bg-yellow-100 text-yellow-800",
};

export default function NewsCard({ article }: { article: any }) {
  const [expanded, setExpanded] = useState(false);
  const color = CATEGORY_COLORS[article.category] ?? CATEGORY_COLORS["Autre"];

  return (
    <div className="bg-white rounded-lg border p-5 shadow-sm space-y-3">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-lg font-semibold leading-snug">{article.title}</h2>
        <span className={`shrink-0 text-xs font-medium px-2 py-1 rounded-full ${color}`}>
          {article.category}
        </span>
      </div>

      <p className="text-gray-600 text-sm">{article.short_description}</p>

      {expanded && (
        <p className="text-gray-700 text-sm border-t pt-3">{article.long_description}</p>
      )}

      <div className="flex items-center justify-between text-xs text-gray-400 pt-1">
        <div className="flex gap-3">
          <span>{article.source_name}</span>
          <span>·</span>
          <span>{new Date(article.published_at).toLocaleDateString("fr-FR")}</span>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-blue-500 hover:underline"
          >
            {expanded ? "Réduire" : "En savoir plus"}
          </button>
          <a
            href={article.article_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 font-medium hover:underline"
          >
            Lire l'article →
          </a>
        </div>
      </div>
    </div>
  );
}
