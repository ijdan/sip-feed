"use client";
import { categoryLabel } from "@/lib/categories";

interface Props {
  categories: string[];
  selected: string | null;
  onChange: (cat: string | null) => void;
  counts: Record<string, number>;
  lang?: "fr" | "en";
}

export default function CategoryFilter({ categories, selected, onChange, counts, lang = "fr" }: Props) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-wrap gap-2">
      {[null, ...categories].map((cat) => {
        const isSelected = selected === cat;
        const label = cat === null
          ? (lang === "en" ? "All" : "Toutes")
          : categoryLabel(cat, lang);
        const count = cat === null ? total : counts[cat] ?? 0;
        return (
          <button
            key={cat ?? "__all__"}
            onClick={() => onChange(cat === selected ? null : cat)}
            className="px-3 py-1 rounded-full text-sm border transition"
            style={isSelected
              ? { backgroundColor: "var(--text)", color: "var(--bg)", borderColor: "var(--text)" }
              : { backgroundColor: "var(--surface)", color: "var(--text-muted)", borderColor: "var(--border)" }
            }
          >
            {label} {count > 0 && <span className="ml-1 opacity-60">({count})</span>}
          </button>
        );
      })}
    </div>
  );
}
