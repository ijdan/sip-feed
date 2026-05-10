"use client";
import { useState, useEffect, useRef } from "react";

export interface FilterItem {
  key: string;
  label: string;
  count?: number;
}

interface Props {
  label: string;
  items: FilterItem[];
  excluded: Set<string>;
  onToggle: (key: string) => void;
}

export default function DropdownFilter({ label, items, excluded, onToggle }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hasFilter = excluded.size > 0;
  const visibleCount = items.filter(i => !excluded.has(i.key)).length;

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

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
        {label}
        {hasFilter && (
          <span className="text-xs opacity-70">{visibleCount}/{items.length}</span>
        )}
        <span className="text-xs opacity-40 ml-1">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          className="absolute left-0 top-full mt-2 min-w-52 rounded-lg border shadow-lg z-50 py-1 max-h-72 overflow-y-auto"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
        >
          {items.map(({ key, label: itemLabel, count }) => (
            <label
              key={key}
              className="flex items-center gap-3 px-4 py-2 cursor-pointer transition hover:opacity-70 text-sm"
              style={{ color: "var(--text)" }}
            >
              <input
                type="checkbox"
                checked={!excluded.has(key)}
                onChange={() => onToggle(key)}
                className="w-4 h-4 accent-current"
              />
              <span className="flex-1">{itemLabel}</span>
              {count !== undefined && (
                <span className="text-xs opacity-40">({count})</span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
