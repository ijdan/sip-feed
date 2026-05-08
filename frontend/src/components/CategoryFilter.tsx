"use client";

interface Props {
  categories: string[];
  selected: string | null;
  onChange: (cat: string | null) => void;
  counts: Record<string, number>;
}

export default function CategoryFilter({ categories, selected, onChange, counts }: Props) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onChange(null)}
        className={`px-3 py-1 rounded-full text-sm border transition ${
          selected === null
            ? "bg-gray-900 text-white border-gray-900"
            : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
        }`}
      >
        Toutes {total > 0 && <span className="ml-1 opacity-70">({total})</span>}
      </button>
      {categories.map((cat) => (
        <button
          key={cat}
          onClick={() => onChange(cat === selected ? null : cat)}
          className={`px-3 py-1 rounded-full text-sm border transition ${
            selected === cat
              ? "bg-gray-900 text-white border-gray-900"
              : "bg-white text-gray-600 border-gray-300 hover:border-gray-500"
          }`}
        >
          {cat} {counts[cat] > 0 && <span className="ml-1 opacity-70">({counts[cat]})</span>}
        </button>
      ))}
    </div>
  );
}
