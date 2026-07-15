"use client";
import { useState } from "react";
import { categoryLabel } from "@/lib/categories";
import { useDragSwipe } from "@/lib/useDragSwipe";
import { formatDate } from "@/lib/types";

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
  onDismiss?: () => void;
  onFavorite?: () => void;
  onReadingList?: () => void;
  onMarkRead?: () => void;
  onSummarize?: () => void;
  isFavorite?: boolean;
  isInReadingList?: boolean;
  isRead?: boolean;
  isAdmin?: boolean;
}

export default function NewsCard({
  article, lang = "fr",
  onDismiss, onFavorite, onReadingList, onMarkRead, onSummarize,
  isFavorite = false, isInReadingList = false, isRead = false, isAdmin = false,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const color = CATEGORY_COLORS[article.category] ?? CATEGORY_COLORS["Autre"];

  const { dragX, dragging, dismissed, swipingLeft, swipingRight, leftProgress, rightProgress, handlers } = useDragSwipe({
    onDismiss: () => { setMenuOpen(false); onDismiss?.(); },
    onMarkRead,
    isRead,
  });

  const title = lang === "en" ? (article.title_en || article.title) : (article.title_fr || article.title);
  const shortDesc = lang === "en" ? (article.short_description_en || article.short_description) : (article.short_description_fr || article.short_description);
  const longDesc = lang === "en" ? (article.long_description_en || article.long_description) : (article.long_description_fr || article.long_description);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    const text = [title, longDesc || shortDesc, article.article_url].filter(Boolean).join("\n----------\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setMenuOpen(false);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* Fond suppression (droite→gauche) */}
      {swipingLeft && (
        <div
          className="absolute inset-0 flex items-center justify-end pr-5 rounded-lg font-semibold text-sm"
          style={{
            backgroundColor: `rgba(220,38,38,${leftProgress * 0.85})`,
            color: "white",
            opacity: leftProgress,
          }}
        >
          {lang === "en" ? "Delete" : "Suppression"} ✕
        </div>
      )}
      {/* Fond lu (gauche→droite) */}
      {swipingRight && (
        <div
          className="absolute inset-0 flex items-center justify-start pl-5 rounded-lg font-semibold text-sm"
          style={{
            backgroundColor: isRead
              ? `rgba(156,163,175,${rightProgress * 0.7})`
              : `rgba(34,197,94,${rightProgress * 0.7})`,
            color: "white",
            opacity: rightProgress,
          }}
        >
          {isRead
            ? (lang === "en" ? "↩ Unread" : "↩ Non lu")
            : (lang === "en" ? "✓ Read" : "✓ Lu")}
        </div>
      )}

      {/* Carte */}
      <div
        style={{
          backgroundColor: "var(--surface)", borderColor: "var(--border)",
          transform: dismissed ? "translateX(-110%)" : `translateX(${dragX}px)`,
          opacity: dismissed ? 0 : isRead ? 0.45 : 1,
          transition: dragging ? "none" : "transform 0.25s ease, opacity 0.25s ease",
          cursor: dragX !== 0 ? "grabbing" : "auto",
        }}
        className="relative rounded-lg border p-5 shadow-sm space-y-3 group select-none"
        {...handlers}
      >
        {/* Bouton menu ⋯ */}
        <div className="absolute top-2 right-2 flex items-center gap-1">
          {copied && (
            <span className="text-xs font-medium px-2 py-1 rounded-full" style={{ color: "#22c55e", backgroundColor: "var(--surface-2)" }}>
              {lang === "en" ? "Copied!" : "Copié !"}
            </span>
          )}
          {menuOpen && (
            <div
              className="flex items-center gap-3 px-4 py-2 rounded-full border shadow-sm"
              style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
            >
              <button onClick={(e) => { e.stopPropagation(); onFavorite?.(); }} title="Favoris"
                className="text-lg transition hover:scale-125" style={{ opacity: isFavorite ? 1 : 0.3 }}>⭐</button>
              <button onClick={(e) => { e.stopPropagation(); onReadingList?.(); }} title="Liste de lecture"
                className="text-lg transition hover:scale-125" style={{ opacity: isInReadingList ? 1 : 0.3 }}>👓</button>
              <button onClick={handleCopy} title={lang === "en" ? "Copy" : "Copier"}
                className="text-lg transition hover:scale-125">📋</button>
              {isAdmin && (
                <button
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onSummarize?.(); }}
                  title={lang === "en" ? "Generate LinkedIn post" : "Générer un post LinkedIn"}
                  className="text-lg transition hover:scale-125"
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="#0A66C2" aria-hidden="true">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z" />
                  </svg>
                </button>
              )}
            </div>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
            title="Options"
            className="w-6 h-6 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 transition-opacity text-sm font-bold tracking-widest"
            style={{ color: "var(--text-muted)", backgroundColor: "var(--surface-2)" }}
          >•••</button>
        </div>

        <div className="flex items-start justify-between gap-4 cursor-pointer pr-8"
          onClick={() => { setMenuOpen(false); setExpanded(!expanded); }}>
          <h2 className="text-lg font-semibold leading-snug" style={{ color: "var(--text)" }}>{title}</h2>
          <span className={`shrink-0 text-xs font-medium px-2 py-1 rounded-full ${color}`}>
            {categoryLabel(article.category, lang)}
          </span>
        </div>

        <p className="text-sm cursor-pointer" style={{ color: "var(--text-muted)" }}
          onClick={() => { setMenuOpen(false); setExpanded(!expanded); }}>{shortDesc}</p>

        {expanded && longDesc && (
          <p className="text-sm pt-3 border-t" style={{ color: "var(--text)", borderColor: "var(--border)" }}>{longDesc}</p>
        )}

        <div className="flex items-center justify-between text-xs pt-1" style={{ color: "var(--text-muted)" }}>
          <div className="flex gap-3">
            <span>{article.source_name}</span><span>·</span>
            <span>{formatDate(article.published_at, lang)}</span>
            {isRead && <span className="opacity-50">· {lang === "en" ? "Read" : "Lu"}</span>}
          </div>
          <a href={article.article_url} target="_blank" rel="noopener noreferrer"
            className="font-medium hover:underline" style={{ color: "var(--accent)" }}
            onClick={(e) => e.stopPropagation()}>
            {lang === "en" ? "Read article →" : "Lire l'article →"}
          </a>
        </div>
      </div>
    </div>
  );
}
