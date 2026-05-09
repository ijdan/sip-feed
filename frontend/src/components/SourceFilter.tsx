"use client";

interface Props {
  sources: string[];
  counts: Record<string, number>;
  excluded: Set<string>;
  onToggle: (source: string) => void;
}

export default function SourceFilter({ sources, counts, excluded, onToggle }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <span className="text-xs shrink-0" style={{ color: "var(--text-muted)" }}>
        Sources :
      </span>
      {sources.map((source) => {
        const active = !excluded.has(source);
        return (
          <button
            key={source}
            onClick={() => onToggle(source)}
            title={active ? `Masquer ${source}` : `Afficher ${source}`}
            className="px-2 py-0.5 rounded-full text-xs border transition"
            style={active
              ? { backgroundColor: "var(--surface)", color: "var(--text)", borderColor: "var(--border)" }
              : { backgroundColor: "transparent", color: "var(--text-muted)", borderColor: "var(--border)", textDecoration: "line-through", opacity: 0.5 }
            }
          >
            {source}{counts[source] ? <span className="ml-1 opacity-60">({counts[source]})</span> : null}
          </button>
        );
      })}
    </div>
  );
}
