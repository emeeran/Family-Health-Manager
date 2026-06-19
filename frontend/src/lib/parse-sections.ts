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

export function parseSections(markdown: string): InsightSection[] {
  const parts = markdown.split(/(?=^(?:\d+\.\s*\*{1,2}|#{1,3}\s))/m);
  const sections: InsightSection[] = [];
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    let title = "";
    let body = trimmed;
    const headingMatch = trimmed.match(
      /^(?:#{1,3}\s*|\d+\.\s*\*{0,2})(.+?)(?:\*{0,2}(?:\s+[-:—]\s*|[-:—]\s+)|\n)/
    );
    if (headingMatch) {
      title = headingMatch[1]
        .replace(/\*+/g, "")
        .replace(/\s*[-:—]\s*$/, "")
        .trim();
      body = trimmed.slice(headingMatch[0].length).trim();
    } else {
      const firstNewline = trimmed.indexOf("\n");
      if (firstNewline > 0 && firstNewline < 80) {
        title = trimmed
          .slice(0, firstNewline)
          .replace(/^[#\d.*\s]+/, "")
          .replace(/\*+/g, "")
          .trim();
        body = trimmed.slice(firstNewline + 1).trim();
      }
    }
    if (title && body) sections.push({ title, body, key: sectionKey(title) });
  }
  if (sections.length === 0)
    sections.push({ title: "Health Insights", body: markdown, key: "other" });
  return sections;
}
