"use client";
import { useDragSwipe } from "@/lib/useDragSwipe";
import { categoryLabel } from "@/lib/categories";

const RESTORE_THRESHOLD = 100;

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
  onRestore: () => void;
}

export default function TrashCard({ article, lang = "fr", onRestore }: Props) {
  const color = CATEGORY_COLORS[article.category] ?? CATEGORY_COLORS["Autre"];
  const title = lang === "en" ? (article.title_en || article.title) : (article.title_fr || article.title);
  const shortDesc = lang === "en"
    ? (article.short_description_en || article.short_description)
    : (article.short_description_fr || article.short_description);

  const { dragX, dismissed: restoring, swipingLeft, leftProgress: progress, handlers } = useDragSwipe({
    dismissThreshold: RESTORE_THRESHOLD,
    onDismiss: onRestore, // dans la corbeille, swipe = restaurer
  });

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* Fond restauration */}
      {dragX < -15 && (
        <div
          className="absolute inset-0 flex items-center justify-end pr-5 rounded-lg font-semibold text-sm"
          style={{
            backgroundColor: `rgba(34,197,94,${progress * 0.85})`,
            color: "white",
            opacity: progress,
          }}
        >
          {lang === "en" ? "Restore ↩" : "Restaurer ↩"}
        </div>
      )}

      <div
        style={{
          backgroundColor: "var(--surface)",
          borderColor: "var(--border)",
          transform: restoring ? "translateX(-110%)" : `translateX(${dragX}px)`,
          opacity: restoring ? 0 : 0.45,
          transition: dragX !== 0 ? "none" : "transform 0.25s ease, opacity 0.25s ease",
          cursor: dragX < 0 ? "grabbing" : "auto",
        }}
        className="rounded-lg border p-4 space-y-2 select-none"
        {...handlers}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-sm font-semibold leading-snug" style={{ color: "var(--text)" }}>{title}</h2>
          <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
            {categoryLabel(article.category, lang)}
          </span>
        </div>
        {shortDesc && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>{shortDesc}</p>
        )}
        <div className="flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
          <span>{article.source_name}</span>
          <span>{new Date(article.published_at).toLocaleDateString("fr-FR")}</span>
        </div>
      </div>
    </div>
  );
}
