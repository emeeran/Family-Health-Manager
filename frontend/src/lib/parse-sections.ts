/**
 * Canonical home for insight markdown section parsing.
 *
 * The backend also returns a pre-parsed `sections` array (with a stable
 * `key` per section); viewers prefer that and fall back to `parseSections`
 * when it is absent. `insight-report-viewer.tsx` re-exports this so existing
 * callers (`overview-tab`, `ai-assistant-tab`) keep their import path.
 */
export interface InsightSection {
  title: string;
  body: string;
  /** Styling key (overview|conditions|labs|risk|recommendations|follow_up|other). */
  key?: string;
}

/** Map a section title to a stable styling key (mirrors the backend parser). */
export function sectionKey(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("overview")) return "overview";
  if (t.includes("active condition") || t.includes("conditions")) return "conditions";
  if (t.includes("lab")) return "labs";
  if (t.includes("risk")) return "risk";
  if (t.includes("recommend")) return "recommendations";
  if (t.includes("follow")) return "follow_up";
  return "other";
}

/** Strip leading/trailing markdown markers and a leading "N." from a heading line. */
function cleanHeading(line: string): string {
  return line
    .replace(/^[*\s#]+/, "") // leading *, #, space
    .replace(/^\d+\.\s*/, "") // leading "N. "
    .replace(/\*+/g, "") // any remaining bold markers
    .replace(/\s*[-:—]\s*$/, "") // trailing " -" / ":"
    .trim();
}

export function parseSections(markdown: string): InsightSection[] {
  if (!markdown || !markdown.trim()) return [];
  // Split before each heading line. The model emits headings in several shapes —
  // "**1. Title**" (stars wrap the whole line), "1. **Title**", "### Title", or
  // plain "1. Title" — so match an optional leading "**" + "N." or a "#" prefix.
  const parts = markdown.split(/(?=^(?:\*{0,2}\s*\d+\.\s|#{1,3}\s))/m);
  const sections: InsightSection[] = [];
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const nl = trimmed.indexOf("\n");
    let title = "";
    let body = "";
    if (nl === -1) {
      title = cleanHeading(trimmed);
    } else {
      title = cleanHeading(trimmed.slice(0, nl));
      body = trimmed.slice(nl + 1).trim();
    }
    if (title && body) sections.push({ title, body, key: sectionKey(title) });
  }
  if (sections.length === 0)
    sections.push({ title: "Health Insights", body: markdown.trim(), key: "other" });
  return sections;
}
