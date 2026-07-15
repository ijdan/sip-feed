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

  const { data, isLoading, mutate } = useSWR(
    token && role === "admin" ? "admin-syntheses" : null,
    () => fetch(`${API}/admin/syntheses`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  );

  const { addFavorite } = usePreferences();

  const [generating, setGenerating] = useState(false);
  const [generateMsg, setGenerateMsg] = useState("");

  const launchGeneration = async () => {
    if (!token || generating) return;
    setGenerating(true);
    setGenerateMsg("Génération en cours… (~1 à 2 min)");
    const previousLatest = data?.syntheses?.[0]?.generated_at ?? null;
    try {
      const res = await fetch(`${API}/admin/synthesis/generate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const detail = (await res.json().catch(() => null))?.detail;
        throw new Error(detail || `HTTP ${res.status}`);
      }
      // Le job est asynchrone : on re-interroge jusqu'à voir une synthèse
      // plus récente (toutes les 10 s, abandon après 5 min).
      const startedAt = Date.now();
      const poll = async () => {
        const fresh = await mutate();
        const latest = fresh?.syntheses?.[0]?.generated_at ?? null;
        if (latest && latest !== previousLatest) {
          setGenerating(false);
          setGenerateMsg("✓ Synthèse générée");
          setTimeout(() => setGenerateMsg(""), 4000);
          return;
        }
        if (Date.now() - startedAt > 5 * 60_000) {
          setGenerating(false);
          setGenerateMsg("⚠️ Pas de nouvelle synthèse après 5 min — consultez le rapport de run.");
          setTimeout(() => setGenerateMsg(""), 8000);
          return;
        }
        setTimeout(poll, 10_000);
      };
      setTimeout(poll, 10_000);
    } catch (err: any) {
      setGenerating(false);
      setGenerateMsg(`✗ ${err.message || "Erreur lors du déclenchement"}`);
      setTimeout(() => setGenerateMsg(""), 6000);
    }
  };

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

  const handleSummarize = async (article: any) => {
    if (!token) return;
    if (summaryData && summaryArticleId === article.id) {
      setSummaryOpen(true);
      return;
    }
    setSummaryLoading(true);
    setSummaryProgressMsg("Initialisation…");
    setSummaryError("");
    setSummaryArticleId(article.id);
    try {
      const res = await fetch(
        `${API}/articles/${article.id}/summary`,
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
        />
      )}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Synthèse</h1>
        <div className="flex items-center gap-3 flex-wrap">
          {generateMsg && (
            <span className="text-sm font-medium"
              style={{ color: generateMsg.startsWith("✓") ? "#22c55e"
                : generateMsg.startsWith("✗") ? "#ef4444" : "var(--text-muted)" }}>
              {generating && <span className="inline-block animate-spin mr-1">⟳</span>}
              {generateMsg}
            </span>
          )}
          <button
            onClick={launchGeneration}
            disabled={generating}
            title="Régénère la synthèse du jour sans lancer de collecte (consomme des tokens LLM)"
            className="px-4 py-2 rounded text-sm font-medium transition disabled:opacity-50"
            style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
          >
            {generating ? "Génération…" : "⚡ Générer maintenant"}
          </button>
          <button onClick={() => mutate()}
            className="text-sm hover:underline"
            style={{ color: "var(--text-muted)" }}>
            Rafraîchir
          </button>
        </div>
      </div>

      {syntheses.length === 0 ? (
        <div className="rounded-xl border p-8 text-center"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
          <p className="text-lg mb-2" style={{ color: "var(--text)" }}>Aucune synthèse disponible</p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Renseignez un centre d'intérêt dans la section « Synthèse du jour » de la console admin et lancez une collecte.
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
                  {" · "}{new Date(s.generated_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
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
                className="px-4 py-2 rounded text-sm font-medium transition hover:opacity-80 disabled:opacity-50"
                style={{ backgroundColor: "var(--accent)", color: "#fff" }}>
                {summaryLoading && summaryArticleId === modalArticle.id ? "…" : "✨ Résumé IA"}
              </button>
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
