"use client";
import { useState, useRef, useEffect, useCallback } from "react";

interface Props {
  terms: string[];
  onAdd: (term: string) => void;
  onRemove: (term: string) => void;
  suggestions: string[];
  lang?: "fr" | "en";
}

const MIN_CHARS = 2; // nombre de caractères avant d'afficher les suggestions
const MAX_SUGGESTIONS = 8;

export default function SearchBar({ terms, onAdd, onRemove, suggestions, lang = "fr" }: Props) {
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fermer le dropdown au clic extérieur
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Suggestions filtrées : contiennent les lettres saisies, pas déjà sélectionnées
  const filtered = input.length >= MIN_CHARS
    ? suggestions
        .filter(s =>
          s.toLowerCase().includes(input.toLowerCase()) &&
          !terms.map(t => t.toLowerCase()).includes(s.toLowerCase())
        )
        .slice(0, MAX_SUGGESTIONS)
    : [];

  const addTerm = useCallback((term: string) => {
    const clean = term.trim();
    if (clean && !terms.map(t => t.toLowerCase()).includes(clean.toLowerCase())) {
      onAdd(clean);
    }
    setInput("");
    setOpen(false);
    setHighlightedIndex(-1);
    inputRef.current?.focus();
  }, [terms, onAdd]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (open && filtered.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightedIndex(i => Math.min(i + 1, filtered.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightedIndex(i => Math.max(i - 1, -1));
        return;
      }
      if (e.key === "Enter" && highlightedIndex >= 0) {
        e.preventDefault();
        addTerm(filtered[highlightedIndex]);
        return;
      }
    }
    if (e.key === "Enter" && input.trim() && highlightedIndex < 0) {
      e.preventDefault();
      addTerm(input.trim());
    }
    if (e.key === "Backspace" && !input && terms.length > 0) {
      onRemove(terms[terms.length - 1]);
    }
    if (e.key === "Escape") {
      setOpen(false);
      setInput("");
      setHighlightedIndex(-1);
    }
  };

  // Réinitialise l'index quand les suggestions changent
  useEffect(() => { setHighlightedIndex(-1); }, [input]);

  const placeholder = terms.length === 0
    ? (lang === "en" ? "Search keywords…" : "Rechercher par mots-clés…")
    : "";

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        className="flex flex-wrap items-center gap-1.5 px-3 py-2 rounded-lg border min-h-[40px] cursor-text"
        style={{ backgroundColor: "var(--surface)", borderColor: open ? "var(--accent)" : "var(--border)" }}
        onClick={() => inputRef.current?.focus()}
      >
        {/* Icône loupe */}
        <span className="text-sm shrink-0" style={{ color: "var(--text-muted)" }}>🔍</span>

        {/* Tags sélectionnés */}
        {terms.map(term => (
          <span
            key={term}
            className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
            style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}
          >
            {term}
            <button
              onClick={(e) => { e.stopPropagation(); onRemove(term); }}
              className="hover:opacity-70 transition-opacity leading-none"
            >×</button>
          </span>
        ))}

        {/* Input */}
        <input
          ref={inputRef}
          value={input}
          onChange={e => { setInput(e.target.value); setOpen(true); }}
          onKeyDown={handleKeyDown}
          onFocus={() => input.length >= MIN_CHARS && setOpen(true)}
          placeholder={placeholder}
          className="flex-1 min-w-[120px] bg-transparent outline-none text-sm"
          style={{ color: "var(--text)" }}
        />

        {/* Effacer tout */}
        {(terms.length > 0 || input) && (
          <button
            onClick={() => { onRemove("__all__"); setInput(""); setOpen(false); }}
            className="text-xs shrink-0 hover:opacity-70 transition-opacity"
            style={{ color: "var(--text-muted)" }}
          >✕</button>
        )}
      </div>

      {/* Dropdown suggestions */}
      {open && filtered.length > 0 && (
        <div
          className="absolute left-0 right-0 top-full mt-1 rounded-lg border shadow-lg z-50 overflow-hidden"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
        >
          {filtered.map((s, idx) => {
            const charIdx = s.toLowerCase().indexOf(input.toLowerCase());
            const isHighlighted = idx === highlightedIndex;
            return (
              <button
                key={s}
                onMouseDown={(e) => { e.preventDefault(); addTerm(s); }}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className="w-full px-4 py-2 text-sm text-left flex items-center gap-2 transition-colors"
                style={{
                  color: "var(--text)",
                  backgroundColor: isHighlighted ? "var(--surface-2)" : "transparent",
                }}
              >
                <span style={{ color: "var(--text-muted)" }}>🔖</span>
                {/* Highlight des lettres correspondantes */}
                <span>
                  {s.slice(0, charIdx)}
                  <strong style={{ color: "var(--accent)" }}>{s.slice(charIdx, charIdx + input.length)}</strong>
                  {s.slice(charIdx + input.length)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
