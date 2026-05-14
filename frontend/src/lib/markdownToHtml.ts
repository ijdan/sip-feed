/**
 * Transforme du Markdown simple en HTML sans librairie externe.
 * Couvre : titres, gras, italique, listes, paragraphes, émojis.
 */
export function markdownToHtml(md: string): string {
  if (!md) return "";

  const lines = md.split("\n");
  const result: string[] = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Ferme la liste si la ligne n'est pas un item
    if (inList && !line.match(/^[\-\*]\s/)) {
      result.push("</ul>");
      inList = false;
    }

    // Titres
    if (line.startsWith("### ")) {
      result.push(`<h3>${inline(line.slice(4))}</h3>`);
    } else if (line.startsWith("## ")) {
      result.push(`<h2>${inline(line.slice(3))}</h2>`);
    } else if (line.startsWith("# ")) {
      result.push(`<h1>${inline(line.slice(2))}</h1>`);
    }
    // Listes
    else if (line.match(/^[\-\*]\s/)) {
      if (!inList) { result.push("<ul>"); inList = true; }
      result.push(`<li>${inline(line.slice(2))}</li>`);
    }
    // Ligne vide → séparateur de paragraphe
    else if (line.trim() === "") {
      result.push("");
    }
    // Paragraphe normal
    else {
      result.push(`<p>${inline(line)}</p>`);
    }
  }

  if (inList) result.push("</ul>");

  return result.join("\n");
}

/** Transforme les éléments inline : **gras**, *italique*, `code` */
function inline(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}
