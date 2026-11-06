"use client";
/** Affiché quand le rendu serveur échoue (backend injoignable, erreur API…). */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="space-y-3 py-8 text-center">
      <p style={{ color: "var(--text)" }}>Impossible de charger les articles pour le moment.</p>
      {error.digest && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>Référence : {error.digest}</p>
      )}
      <button
        onClick={reset}
        className="px-4 py-2 rounded-md border text-sm"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)", color: "var(--text)" }}
      >
        Réessayer
      </button>
    </div>
  );
}
