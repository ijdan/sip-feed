import DOMPurify from "dompurify";

/**
 * Transforme du Markdown simple en HTML sans librairie externe.
 * Couvre : titres, gras, italique, listes, paragraphes, émojis.
 * La sortie est passée à DOMPurify pour neutraliser tout HTML injecté
 * (la source provient d'un LLM nourri par du contenu scrapé non-fiable).
 */
export function markdownToHtml(md: string): string {
  if (!md) return "";

  // Le texte source peut contenir du HTML injecté : on escape les chevrons
  // AVANT la conversion markdown, sinon nos <strong> légitimes seraient
  // également escapés. DOMPurify reste un filet de sécurité en sortie.
  const safe = escapeHtml(md);

  const lines = safe.split("\n");
  const result: string[] = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (inList && !line.match(/^[\-\*]\s/)) {
      result.push("</ul>");
      inList = false;
    }

    if (line.startsWith("### ")) {
      result.push(`<h3>${inline(line.slice(4))}</h3>`);
    } else if (line.startsWith("## ")) {
      result.push(`<h2>${inline(line.slice(3))}</h2>`);
    } else if (line.startsWith("# ")) {
      result.push(`<h1>${inline(line.slice(2))}</h1>`);
    } else if (line.match(/^[\-\*]\s/)) {
      if (!inList) { result.push("<ul>"); inList = true; }
      result.push(`<li>${inline(line.slice(2))}</li>`);
    } else if (line.trim() === "") {
      result.push("");
    } else {
      result.push(`<p>${inline(line)}</p>`);
    }
  }

  if (inList) result.push("</ul>");

  const html = result.join("\n");

  // SSR safety: DOMPurify a besoin de window. Côté serveur on retourne
  // le HTML déjà escape-only (sans formattage actif), ce qui reste safe.
  if (typeof window === "undefined") return html;
  return DOMPurify.sanitize(html);
}

/** Escape les caractères HTML dangereux avant conversion markdown. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Transforme les éléments inline : **gras**, *italique*, `code` */
function inline(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}
