/**
 * Pure selection helpers for the insight {@link StreamingPreview}.
 *
 * Extracted from the component so the branching (which icon/accent for a stage
 * label; whether the stream has formed real section headings yet) is
 * unit-testable without a DOM/render harness. Every function is total and
 * side-effect-free.
 */

import { parseSections } from "@/lib/parse-sections";

export type StageKind = "context" | "cloud" | "local";

/**
 * Classify a streaming stage label so the preview can pick an icon + accent.
 * Stage strings come from the backend SSE frames, e.g.
 * "Loading patient records…", "Generating via Cloud AI…",
 * "Generating via Ollama qwen3:4b…".
 */
export function classifyStage(stage: string): StageKind {
  const s = (stage ?? "").toLowerCase();
  if (
    s.includes("context") ||
    s.includes("loading") ||
    s.includes("preparing") ||
    s.includes("saving")
  ) {
    return "context";
  }
  if (s.includes("cloud")) {
    return "cloud";
  }
  return "local";
}

/**
 * True when the accumulated stream already contains at least one real section
 * heading, so the preview should render structured blocks instead of raw text.
 * `parseSections` returns a single fallback "Health Insights" section when no
 * heading has been emitted yet — that case is treated as "no structure".
 */
export function hasStructuredContent(text: string): boolean {
  const sections = parseSections(text ?? "");
  return sections.length > 1 || (sections.length === 1 && sections[0].title !== "Health Insights");
}
