/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Mode clair — tons chauds, reposants
        light: { bg: "#f5f0e8", surface: "#ffffff", muted: "#f0ebe3" },
        // Mode sombre — ardoise bleutée, pas de noir pur
        dark: { bg: "#16171c", surface: "#1e2028", muted: "#252836" },
      },
    },
  },
  plugins: [],
};
