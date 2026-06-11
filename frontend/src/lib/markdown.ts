/**
 * Minimal markdown → HTML for consultation summaries.
 *
 * Escapes raw HTML first to prevent XSS when rendered via dangerouslySetInnerHTML.
 * Supports: headings, bold, unordered lists, tables.
 */
export function simpleMarkdown(md: string): string {
  // Escape raw HTML to prevent XSS (the AI output should be markdown, not HTML)
  let html = md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Tables
  html = html.replace(
    /^\|(.+)\|\s*\n\|[-| :]+\|\s*\n((?:\|.+\|\s*\n)*)/gm,
    (_match, header: string, body: string) => {
      const ths = header
        .split("|")
        .map((c: string) => `<th>${c.trim()}</th>`)
        .join("");
      const rows = body
        .trim()
        .split("\n")
        .map((row: string) => {
          const tds = row
            .replace(/^\|/, "")
            .replace(/\|$/, "")
            .split("|")
            .map((c: string) => `<td>${c.trim()}</td>`)
            .join("");
          return `<tr>${tds}</tr>`;
        })
        .join("");
      return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
    }
  );

  // Headings
  html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");

  // Wrap loose lines in paragraphs (skip blocks that already have HTML tags)
  html = html
    .replace(/(<(h[1-6]|li|table|tr|td|th|thead|tbody)[^>]*>)/g, "\n$1")
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      if (/^<(h[1-6]|li|table|ul|ol)/.test(trimmed)) return trimmed;
      return `<p>${trimmed}</p>`;
    })
    .join("\n");

  return html;
}
