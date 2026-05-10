"use client";
import { useSettings } from "@/lib/useSettings";

type FontSize = "sm" | "md" | "lg";
const FONT_SIZES: { key: FontSize; px: number }[] = [
  { key: "sm", px: 12 },
  { key: "md", px: 16 },
  { key: "lg", px: 22 },
];

export default function Controls() {
  const { settings, update } = useSettings();
  const dark = settings.theme === "dark";
  const fontSize = settings.font_size as FontSize;

  const toggleTheme = () => update({ theme: dark ? "light" : "dark" });
  const changeFont = (size: FontSize) => update({ font_size: size });

  const btnBase = "flex items-center justify-center rounded transition";

  return (
    <div className="flex items-center gap-2">
      {/* Sélecteur taille de police */}
      <div className="flex items-center border rounded-md overflow-hidden"
        style={{ borderColor: "var(--border)" }}>
        {FONT_SIZES.map(({ key, px }) => (
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
            A
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
