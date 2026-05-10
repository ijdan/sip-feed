"use client";
import { useState, useRef } from "react";
import { categoryLabel } from "@/lib/categories";

const DISMISS_THRESHOLD = 120;

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
  isFavorite?: boolean;
  isInReadingList?: boolean;
}

export default function NewsCard({
  article, lang = "fr",
  onDismiss, onFavorite, onReadingList,
  isFavorite = false, isInReadingList = false,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [dismissed, setDismissedAnim] = useState(false);
  const startX = useRef(0);
  const color = CATEGORY_COLORS[article.category] ?? CATEGORY_COLORS["Autre"];

  const triggerDismiss = () => {
    setDismissedAnim(true);
    setMenuOpen(false);
    setTimeout(() => onDismiss?.(), 250);
  };

  const onDragStart = (clientX: number) => { startX.current = clientX; setDragging(true); };
  const onDragMove = (clientX: number) => {
    if (!dragging) return;
    const delta = clientX - startX.current;
    if (delta < 0) setDragX(delta);
  };
  const onDragEnd = () => {
    if (dragX < -DISMISS_THRESHOLD) triggerDismiss();
    else setDragX(0);
    setDragging(false);
  };

  const title = lang === "en" ? (article.title_en || article.title) : (article.title_fr || article.title);
  const shortDesc = lang === "en" ? (article.short_description_en || article.short_description) : (article.short_description_fr || article.short_description);
  const longDesc = lang === "en" ? (article.long_description_en || article.long_description) : (article.long_description_fr || article.long_description);

  return (
    <div
      style={{
        backgroundColor: "var(--surface)", borderColor: "var(--border)",
        transform: dismissed ? "translateX(-110%)" : `translateX(${dragX}px)`,
        opacity: dismissed ? 0 : Math.max(0.3, 1 + dragX / 300),
        transition: dragging ? "none" : "transform 0.25s ease, opacity 0.25s ease",
        cursor: dragX < 0 ? "grabbing" : "auto",
      }}
      className="relative rounded-lg border p-5 shadow-sm space-y-3 group select-none"
      onTouchStart={(e) => onDragStart(e.touches[0].clientX)}
      onTouchMove={(e) => onDragMove(e.touches[0].clientX)}
      onTouchEnd={onDragEnd}
      onMouseDown={(e) => onDragStart(e.clientX)}
      onMouseMove={(e) => onDragMove(e.clientX)}
      onMouseUp={onDragEnd}
      onMouseLeave={() => { if (dragging) onDragEnd(); }}
    >
      {/* Bouton menu ⋯ */}
      <div className="absolute top-2 right-2 flex items-center gap-1">
        {menuOpen && (
          <div
            className="flex items-center gap-3 px-4 py-2 rounded-full border shadow-sm"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
          >
            <button
              onClick={(e) => { e.stopPropagation(); onFavorite?.(); }}
              title="Favoris"
              className="text-lg transition hover:scale-125"
              style={{ opacity: isFavorite ? 1 : 0.3 }}
            >⭐</button>
            <button
              onClick={(e) => { e.stopPropagation(); onReadingList?.(); }}
              title="Liste de lecture"
              className="text-lg transition hover:scale-125"
              style={{ opacity: isInReadingList ? 1 : 0.3 }}
            >👓</button>
            <div style={{ width: "1px", height: "16px", backgroundColor: "var(--border)" }} />
            <button
              onClick={(e) => { e.stopPropagation(); triggerDismiss(); }}
              title="Masquer"
              className="text-base font-bold transition hover:scale-125"
              style={{ color: "var(--text-muted)", opacity: 0.6 }}
            >✕</button>
          </div>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
          title="Options"
          className="w-6 h-6 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 transition-opacity text-sm font-bold tracking-widest"
          style={{ color: "var(--text-muted)", backgroundColor: "var(--surface-2)" }}
        >
          •••
        </button>
      </div>

      <div
        className="flex items-start justify-between gap-4 cursor-pointer pr-8"
        onClick={() => { setMenuOpen(false); setExpanded(!expanded); }}
      >
        <h2 className="text-lg font-semibold leading-snug" style={{ color: "var(--text)" }}>
          {title}
        </h2>
        <span className={`shrink-0 text-xs font-medium px-2 py-1 rounded-full ${color}`}>
          {categoryLabel(article.category, lang)}
        </span>
      </div>

      <p
        className="text-sm cursor-pointer transition-colors"
        style={{ color: "var(--text-muted)" }}
        onClick={() => { setMenuOpen(false); setExpanded(!expanded); }}
      >
        {shortDesc}
      </p>

      {expanded && longDesc && (
        <p className="text-sm pt-3 border-t" style={{ color: "var(--text)", borderColor: "var(--border)" }}>
          {longDesc}
        </p>
      )}

      <div className="flex items-center justify-between text-xs pt-1" style={{ color: "var(--text-muted)" }}>
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
          onClick={(e) => e.stopPropagation()}
        >
          {lang === "en" ? "Read article →" : "Lire l'article →"}
        </a>
      </div>
    </div>
  );
}
