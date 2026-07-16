"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import useSWR from "swr";
import { markdownToHtml } from "@/lib/markdownToHtml";
import SummaryLayer from "@/components/SummaryLayer";
import { usePreferences } from "@/lib/usePreferences";
import { ArticleSummary } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL;

export default function SynthesisPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const token = ((session as unknown) as import("@/lib/types").AppSession)?.accessToken;
  const role = ((session as unknown) as import("@/lib/types").AppSession)?.role;

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && role !== "admin") router.replace("/");
  }, [status, role, router]);

  // Filtre optionnel ?date=YYYY-MM-DD (lien « Voir la synthèse » de l'admin)
  const [dateFilter, setDateFilter] = useState<string | null>(null);
  const [dateFilterReady, setDateFilterReady] = useState(false);
  useEffect(() => {
    const d = new URLSearchParams(window.location.search).get("date");
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) setDateFilter(d);
    setDateFilterReady(true);
  }, []);

  const { data, isLoading, mutate } = useSWR(
    token && role === "admin" && dateFilterReady
      ? `admin-syntheses${dateFilter ? `-${dateFilter}` : ""}`
      : null,
    () => fetch(`${API}/admin/syntheses${dateFilter ? `?date=${dateFilter}` : ""}`,
      { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  );

  const clearDateFilter = () => {
    setDateFilter(null);
    window.history.replaceState(null, "", "/admin/synthesis");
  };

  const { addFavorite } = usePreferences();

  const [modalArticle, setModalArticle] = useState<any>(null);
  const [modalCopied, setModalCopied] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const lang = typeof window !== "undefined"
    ? (localStorage.getItem("feed-lang") as "fr" | "en" || "fr")
    : "fr";

  const [summaryData, setSummaryData] = useState<ArticleSummary | null>(null);
  const [summaryArticleId, setSummaryArticleId] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryProgressMsg, setSummaryProgressMsg] = useState("");
  const [summaryError, setSummaryError] = useState("");

  const handleSummarize = async (article: any, force = false) => {
    if (!token) return;
    if (!force && summaryData && summaryArticleId === article.id) {
      setSummaryOpen(true);
      return;
    }
    setSummaryOpen(false);
    setSummaryLoading(true);
    setSummaryProgressMsg("Initialisation…");
    setSummaryError("");
    setSummaryArticleId(article.id);
    try {
      const res = await fetch(
        `${API}/articles/${article.id}/summary${force ? "?force=true" : ""}`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok || !res.body) throw new Error("Erreur lors de la génération du résumé.");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          const event = JSON.parse(part.slice(6));
          if (event.type === "progress") {
            setSummaryProgressMsg(event.message);
          } else if (event.type === "result") {
            setSummaryData(event.data);
            setSummaryLoading(false);
            setSummaryProgressMsg("");
            setSummaryOpen(true);
            addFavorite(article.id);
            mutate(); // rafraîchit has_summary → le bouton de la popin passe en couleur accent
          } else if (event.type === "error") {
            throw new Error(event.message || "Erreur lors de la génération du résumé.");
          }
        }
      }
    } catch (err: any) {
      setSummaryLoading(false);
      setSummaryProgressMsg("");
      setSummaryError(err.message || "Erreur lors de la génération du résumé.");
      setTimeout(() => setSummaryError(""), 5000);
    }
  };

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) setModalArticle(null);
    };
    if (modalArticle) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modalArticle]);

  useEffect(() => { setModalCopied(false); }, [modalArticle]);

  const handleModalCopy = () => {
    if (!modalArticle) return;
    const title = lang === "en" ? (modalArticle.title_en || modalArticle.title_fr) : (modalArticle.title_fr || modalArticle.title_en);
    const desc = lang === "en"
      ? (modalArticle.long_description_en || modalArticle.short_description_en)
      : (modalArticle.long_description_fr || modalArticle.short_description_fr);
    const text = [title, desc, modalArticle.article_url].filter(Boolean).join("\n----------\n");
    navigator.clipboard.writeText(text);
    setModalCopied(true);
    setTimeout(() => setModalCopied(false), 2000);
  };

  if (status === "loading" || isLoading) {
    return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Chargement…</p>;
  }

  const syntheses = data?.syntheses ?? [];

  return (
    <div className="space-y-6 pb-12">
      {/* Toast résumé */}
      {(summaryLoading || summaryError) && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 px-5 py-3 rounded-full shadow-lg text-sm font-medium flex items-center gap-2"
          style={{
            backgroundColor: summaryError ? "#dc2626" : "var(--text)",
            color: summaryError ? "#fff" : "var(--bg)",
            maxWidth: "calc(100vw - 3rem)",
          }}
        >
          {summaryLoading && <span className="shrink-0 animate-spin">⟳</span>}
          <span className="truncate">{summaryLoading ? summaryProgressMsg : summaryError}</span>
        </div>
      )}

      {/* Layer résumé */}
      {summaryOpen && summaryData && (
        <SummaryLayer
          data={summaryData}
          initialLang={lang}
          onClose={() => setSummaryOpen(false)}
          onRegenerate={() => summaryArticleId && handleSummarize({ id: summaryArticleId }, true)}
        />
      )}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Synthèse</h1>
        <button onClick={() => mutate()}
          className="text-sm hover:underline"
          style={{ color: "var(--text-muted)" }}>
          Rafraîchir
        </button>
      </div>

      {/* Bandeau filtre date (consultation d'une date générée manuellement) */}
      {dateFilter && (
        <div className="rounded-lg border px-4 py-3 flex items-center justify-between gap-4 flex-wrap"
          style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)" }}>
          <span className="text-sm" style={{ color: "var(--text)" }}>
            📅 Synthèse du{" "}
            <strong>{new Date(dateFilter).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</strong>
          </span>
          <button onClick={clearDateFilter}
            className="text-sm hover:underline" style={{ color: "var(--text-muted)" }}>
            Voir les dernières synthèses →
          </button>
        </div>
      )}

      {syntheses.length === 0 ? (
        <div className="rounded-xl border p-8 text-center"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2" style={{ color: "var(--text)" }}>
            {dateFilter ? "Aucune synthèse pour cette date" : "Aucune synthèse disponible"}
          </p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {dateFilter
              ? "Générez-la depuis la section « Synthèse du jour » de la console admin en choisissant cette date."
              : "Renseignez un centre d'intérêt dans la section « Synthèse du jour » de la console admin et lancez une collecte."}
          </p>
        </div>
      ) : (
        syntheses.map((s: any) => (
          <div key={s.date} className="rounded-xl border overflow-hidden"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            {/* En-tête */}
            <div className="px-6 py-4 border-b flex items-center justify-between"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--surface-2)" }}>
              <div>
                <p className="font-semibold" style={{ color: "var(--text)" }}>🎯 {s.interest}</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {new Date(s.date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
                  {" · "}{s.articles_count} articles analysés
                  {s.perimeter_count != null && s.perimeter_count !== s.articles_count &&
                    ` (sur ${s.perimeter_count} dans le périmètre)`}
                  {" · "}
                  {s.generated_at?.slice(0, 10) !== s.date
                    ? `générée a posteriori le ${new Date(s.generated_at).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} à ${new Date(s.generated_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`
                    : new Date(s.generated_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                  {s.usage?.total_tokens > 0 &&
                    ` · ${s.usage.total_tokens.toLocaleString("fr-FR")} tokens LLM`}
                </p>
              </div>
            </div>
            {/* Contenu synthèse — rendu HTML depuis Markdown */}
            <div className="px-6 py-5 text-sm leading-relaxed synthesis-content"
              style={{ color: "var(--text)" }}
              dangerouslySetInnerHTML={{
                __html: s.content?.startsWith("⚠️ Synthèse indisponible")
                  ? `<div style="color:var(--text-muted)">${markdownToHtml(s.content)}</div>`
                  : markdownToHtml(s.content)
              }}
            />

            {/* Articles cités */}
            {s.cited_articles?.length > 0 && (
              <div className="px-6 pb-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
                <p className="text-xs font-medium mb-3" style={{ color: "var(--text-muted)" }}>
                  📎 {s.cited_articles.length} article{s.cited_articles.length > 1 ? "s" : ""} cité{s.cited_articles.length > 1 ? "s" : ""}
                </p>
                <div className="flex flex-wrap gap-2">
                  {s.cited_articles.map((a: any) => (
                    <button
                      key={a.id}
                      onClick={() => setModalArticle(a)}
                      className="text-xs px-3 py-1.5 rounded-full border transition hover:opacity-70 text-left"
                      style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
                    >
                      {lang === "en" ? (a.title_en || a.title_fr) : (a.title_fr || a.title_en)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))
      )}
      {/* Modal article cité */}
      {modalArticle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
          <div ref={modalRef}
            className="w-full max-w-lg rounded-xl border shadow-xl p-6 space-y-4"
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            <div className="flex items-start justify-between gap-4">
              <h3 className="font-semibold text-lg leading-snug" style={{ color: "var(--text)" }}>
                {lang === "en" ? (modalArticle.title_en || modalArticle.title_fr) : (modalArticle.title_fr || modalArticle.title_en)}
              </h3>
              <div className="flex items-center gap-2 shrink-0">
                {modalCopied
                  ? <span className="text-xs font-medium" style={{ color: "#22c55e" }}>Copié !</span>
                  : <button onClick={handleModalCopy} title="Copier"
                      className="text-lg hover:opacity-60 transition"
                      style={{ color: "var(--text-muted)" }}>📋</button>
                }
                <button onClick={() => setModalArticle(null)}
                  className="text-lg hover:opacity-60 transition"
                  style={{ color: "var(--text-muted)" }}>✕</button>
              </div>
            </div>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>{modalArticle.source_name}</p>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>
              {lang === "en"
                ? (modalArticle.long_description_en || modalArticle.short_description_en)
                : (modalArticle.long_description_fr || modalArticle.short_description_fr)}
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={() => { const a = modalArticle; setModalArticle(null); handleSummarize(a); }}
                disabled={summaryLoading}
                title={modalArticle.has_summary
                  ? "Résumé déjà généré — affichage immédiat"
                  : "Résumé pas encore généré — le clic le crée (appel LLM)"}
                className="px-4 py-2 rounded text-sm font-medium transition hover:opacity-80 disabled:opacity-50"
                style={{
                  backgroundColor: modalArticle.has_summary ? "var(--accent)" : "#9ca3af",
                  color: "#fff",
                }}>
                {summaryLoading && summaryArticleId === modalArticle.id ? "…" : "✨ Résumé IA"}
              </button>
              {/* Régénération — uniquement si un résumé existe déjà (qualité parfois insuffisante) */}
              {modalArticle.has_summary && (
                <button
                  onClick={() => { const a = modalArticle; setModalArticle(null); handleSummarize(a, true); }}
                  disabled={summaryLoading}
                  title="Ignorer le résumé existant et en générer un nouveau (appel LLM)"
                  className="px-4 py-2 rounded text-sm font-medium transition hover:opacity-80 disabled:opacity-50 border"
                  style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}>
                  🔄 Régénérer
                </button>
              )}
              <a href={modalArticle.article_url} target="_blank" rel="noopener noreferrer"
                className="inline-block px-4 py-2 rounded text-sm font-medium transition hover:opacity-80"
                style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}>
                {lang === "en" ? "Read article →" : "Lire l'article →"}
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
