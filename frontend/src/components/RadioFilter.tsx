"use client";
import { useState, useEffect, useRef } from "react";
import { FilterItem } from "@/components/DropdownFilter";

interface Props {
  label: string;
  items: FilterItem[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  allLabel?: string;
}

export default function RadioFilter({ label, items, selected, onSelect, allLabel = "Toutes" }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hasFilter = selected !== null;
  const selectedItem = items.find(i => i.key === selected);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (key: string | null) => {
    onSelect(key);
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-sm transition"
        style={{
          borderColor: hasFilter ? "var(--accent)" : "var(--border)",
          color: hasFilter ? "var(--accent)" : "var(--text-muted)",
          backgroundColor: "var(--surface)",
        }}
      >
        {hasFilter ? selectedItem?.label ?? label : label}
        <span className="text-xs opacity-40 ml-1">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          className="absolute left-0 top-full mt-2 min-w-52 rounded-lg border shadow-lg z-50 py-1 max-h-72 overflow-y-auto"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
        >
          {/* Option "Toutes" */}
          <button
            onClick={() => handleSelect(null)}
            className="w-full flex items-center gap-3 px-4 py-2 text-sm transition hover:opacity-70 text-left"
            style={{ color: selected === null ? "var(--accent)" : "var(--text)" }}
          >
            <span className="w-4 h-4 flex items-center justify-center text-xs">
              {selected === null ? "●" : "○"}
            </span>
            <span className="flex-1">{allLabel}</span>
          </button>

          <div className="my-1 border-t" style={{ borderColor: "var(--border)" }} />

          {items.map(({ key, label: itemLabel, count }) => (
            <button
              key={key}
              onClick={() => handleSelect(key)}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm transition hover:opacity-70 text-left"
              style={{ color: selected === key ? "var(--accent)" : "var(--text)" }}
            >
              <span className="w-4 h-4 flex items-center justify-center text-xs">
                {selected === key ? "●" : "○"}
              </span>
              <span className="flex-1">{itemLabel}</span>
              {count !== undefined && (
                <span className="text-xs opacity-40">({count})</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
