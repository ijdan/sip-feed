"use client";
import { useState, useEffect } from "react";
import { ArticleSummary } from "@/lib/types";

interface Props {
  data: ArticleSummary;
  initialLang: "fr" | "en";
  onClose: () => void;
}

export default function SummaryLayer({ data, initialLang, onClose }: Props) {
  const [lang, setLang] = useState<"fr" | "en">(initialLang);
  const [copiedText, setCopiedText] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  const summary = lang === "en" ? data.summary_en : data.summary_fr;
  const wordCount = lang === "en" ? data.word_count_en : data.word_count_fr;

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleCopyText = () => {
    navigator.clipboard.writeText(summary);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(data.article_url);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0" style={{ backgroundColor: "rgba(0,0,0,0.5)" }} />

      <div
        className="relative w-full sm:max-w-3xl max-h-[90vh] sm:max-h-[85vh] flex flex-col rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4 border-b shrink-0 flex-wrap gap-2"
          style={{ borderColor: "var(--border)" }}
        >
          <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
            {lang === "en" ? `Summary · ${wordCount} words` : `Résumé · ${wordCount} mots`}
            {data.cached && (
              <span
                className="ml-2 text-xs px-1.5 py-0.5 rounded"
                style={{ backgroundColor: "var(--surface-2)", color: "var(--text-muted)" }}
              >
                cache
              </span>
            )}
          </span>

          <div className="flex items-center gap-2">
            {/* Toggle FR / EN */}
            <div className="flex border rounded-md overflow-hidden" style={{ borderColor: "var(--border)" }}>
              {(["fr", "en"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  className="px-3 py-1 text-sm font-medium transition"
                  style={
                    lang === l
                      ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                      : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }
                  }
                >
                  {l.toUpperCase()}
                </button>
              ))}
            </div>

            <button
              onClick={handleCopyText}
              title={lang === "en" ? "Copy text" : "Copier le texte"}
              className="px-3 py-1 text-sm rounded-md border transition"
              style={{
                borderColor: "var(--border)",
                backgroundColor: "var(--surface-2)",
                color: copiedText ? "#22c55e" : "var(--text-muted)",
              }}
            >
              {copiedText ? "✓" : "📋"}
            </button>

            <button
              onClick={handleCopyUrl}
              title={lang === "en" ? "Copy URL" : "Copier l'URL"}
              className="px-3 py-1 text-sm rounded-md border transition"
              style={{
                borderColor: "var(--border)",
                backgroundColor: "var(--surface-2)",
                color: copiedUrl ? "#22c55e" : "var(--text-muted)",
              }}
            >
              {copiedUrl ? "✓" : "🔗"}
            </button>

            <button
              onClick={onClose}
              title="Fermer (Échap)"
              className="px-3 py-1 text-sm rounded-md border transition"
              style={{
                borderColor: "var(--border)",
                backgroundColor: "var(--surface-2)",
                color: "var(--text-muted)",
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Contenu */}
        <div className="overflow-y-auto px-6 py-5 flex-1">
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}
          >
            {summary}
          </p>
        </div>

        {/* Footer */}
        <div
          className="px-6 py-3 border-t text-xs shrink-0 flex items-center gap-4"
          style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
        >
          <a
            href={data.article_url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
            style={{ color: "var(--accent)" }}
          >
            {lang === "en" ? "Source article →" : "Article source →"}
          </a>
          <span className="opacity-50">{data.model_used}</span>
        </div>
      </div>
    </div>
  );
}
