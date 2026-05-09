"use client";
import { useEffect, useState } from "react";

type FontSize = "sm" | "md" | "lg";
const FONT_SIZES: { key: FontSize; label: string; px: number }[] = [
  { key: "sm", label: "A", px: 12 },
  { key: "md", label: "A", px: 16 },
  { key: "lg", label: "A", px: 22 },
];

export default function Controls() {
  const [dark, setDark] = useState(false);
  const [fontSize, setFontSize] = useState<FontSize>("md");

  useEffect(() => {
    // Thème
    const savedTheme = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = savedTheme === "dark" || (!savedTheme && prefersDark);
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);

    // Police
    const savedFont = (localStorage.getItem("font-size") ?? "md") as FontSize;
    setFontSize(savedFont);
    applyFont(savedFont);
  }, []);

  const applyFont = (size: FontSize) => {
    document.documentElement.classList.remove("font-size-sm", "font-size-md", "font-size-lg");
    document.documentElement.classList.add(`font-size-${size}`);
  };

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  const changeFont = (size: FontSize) => {
    setFontSize(size);
    applyFont(size);
    localStorage.setItem("font-size", size);
  };

  const btnBase = "flex items-center justify-center rounded transition";

  return (
    <div className="flex items-center gap-2">
      {/* Sélecteur taille de police */}
      <div className="flex items-center border rounded-md overflow-hidden"
        style={{ borderColor: "var(--border)" }}>
        {FONT_SIZES.map(({ key, label, px }) => (
          <button
            key={key}
            onClick={() => changeFont(key)}
            title={key === "sm" ? "Petite" : key === "md" ? "Moyenne" : "Grande"}
            className={`px-2 py-1 ${btnBase} leading-none`}
            style={{
              fontSize: `${px}px`,
              fontWeight: key === "lg" ? 600 : 400,
              ...(fontSize === key
                ? { backgroundColor: "var(--text)", color: "var(--bg)" }
                : { backgroundColor: "var(--surface)", color: "var(--text-muted)" }
              )
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Toggle thème */}
      <button
        onClick={toggleTheme}
        title={dark ? "Mode clair" : "Mode sombre"}
        className={`w-8 h-8 ${btnBase} hover:opacity-80`}
        style={{ backgroundColor: "var(--surface-2)", color: "var(--text)" }}
      >
        {dark ? "☀️" : "🌙"}
      </button>
    </div>
  );
}
