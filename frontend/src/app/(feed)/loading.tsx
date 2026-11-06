/** Squelette affiché pendant le premier rendu serveur du feed. */
export default function Loading() {
  return (
    <div className="space-y-4" aria-busy="true">
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>Chargement…</p>
      <div className="grid gap-4 grid-cols-1">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-32 rounded-lg animate-pulse"
            style={{ backgroundColor: "var(--surface-2)" }}
          />
        ))}
      </div>
    </div>
  );
}
