/**
 * Pure, gracefully-degrading extractors for the AI Health Insights "editorial
 * document" renderer.
 *
 * `COMPREHENSIVE_INSIGHT_PROMPT` emits clinical prose that *embeds* structure —
 * trajectory words, "from X to Y" lab deltas, severity/priority cues, and one
 * paragraph per item. These helpers surface that structure as typed signals so
 * the viewer can render badges/arrows/callouts. **Every** function returns
 * `null` / `[]` / `0` when it finds nothing, so callers always have a safe
 * fallback to plain-prose rendering (the redesign is strictly additive in
 * robustness — worst case equals the previous wall-of-text).
 */

import type { InsightSection } from "@/lib/parse-sections";

export type TrajectoryDir = "up" | "down" | "flat";
export type Tone = "good" | "warn" | "bad";
export interface Trajectory {
  label: string;
  dir: TrajectoryDir;
  tone: Tone;
}

export type Severity = "high" | "moderate" | "low";
export type Priority = "urgent" | "important" | "routine";

export interface LabDelta {
  from: string;
  to: string;
  unit?: string;
  dir: "up" | "down";
}

export interface InsightKpis {
  conditions: number;
  labs: number;
  risks: number;
  followUps: number;
}

// Keyword sets. Word boundaries keep "controlled" from matching inside
// "uncontrolled", etc. Bad-group keywords are checked before good so that
// "suboptimally controlled" / "poorly controlled" never read as "controlled".
const TRAJECTORY_BAD =
  /\b(worsen(?:ing|ed)?|deteriorat(?:e[ds]?|ing|ion)?|suboptimally|uncontrolled|poorly controlled|exacerbat(?:e[ds]?|ing|ion)?|progress(?:ed|ing)?|declin(?:e[ds]?|ing)|advanced|advancing)\b/i;
const TRAJECTORY_GOOD =
  /\b(improv(?:e[ds]?|ing)|better|well[- ]controlled|resolv(?:e[ds]?|ing|ed)?|recover(?:e[ds]?|ing|y)?|controlled)\b/i;
const TRAJECTORY_WARN = /\b(stable|unchanged|persist(?:s|ent|ently)?|maintained|steady)\b/i;

const SEVERITY_HIGH =
  /\b(critical|severe|high(?:ly)?|urgent|markedly|significantly elevated|dangerously|life[- ]threatening)\b/i;
const SEVERITY_MODERATE = /\b(moderate|elevated|borderline|intermediate)\b/i;
// Deliberately narrow — bare "low" collides with "low hemoglobin" (a bad sign).
const SEVERITY_LOW = /\b(mild|minimal|slight)\b/i;

const PRIORITY_URGENT =
  /\b(urgent(?:ly)?|immediately|asap|emergency|emergent|promptly|without delay|right away)\b/i;
const PRIORITY_IMPORTANT =
  /\b(important|soon|discuss|review|schedule|follow[- ]up|follow up|refer|consult)\b/i;
const PRIORITY_ROUTINE =
  /\b(routine|monitor(?:ing)?|annual|regular|continue|ongoing|maintenance)\b/i;

/** Strip `**bold**` / `*italic*` / `` `code` `` markers so keyword scans are clean. */
function stripMarkdown(text: string): string {
  return text.replace(/[*`_]/g, "");
}

/** Split a section body into non-empty paragraph blocks (one block ≈ one item). */
export function splitBlocks(body: string): string[] {
  if (!body) return [];
  return body
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter((b) => b.length > 0);
}

/**
 * Detect a condition's trajectory from its prose. Returns a short label +
 * directional/tone signal for a badge, or `null` when no cue is found.
 */
export function detectTrajectory(text: string): Trajectory | null {
  if (!text) return null;
  const clean = stripMarkdown(text);
  if (TRAJECTORY_BAD.test(clean)) return { label: "Needs attention", dir: "down", tone: "bad" };
  if (TRAJECTORY_GOOD.test(clean)) return { label: "Improving", dir: "up", tone: "good" };
  if (TRAJECTORY_WARN.test(clean)) return { label: "Stable", dir: "flat", tone: "warn" };
  return null;
}

/**
 * Detect the severity of a risk/lab/condition statement. Checked high →
 * moderate → low so the strongest cue wins. Returns `null` when nothing matches.
 */
export function detectSeverity(text: string): Severity | null {
  if (!text) return null;
  const clean = stripMarkdown(text);
  if (SEVERITY_HIGH.test(clean)) return "high";
  if (SEVERITY_MODERATE.test(clean)) return "moderate";
  if (SEVERITY_LOW.test(clean)) return "low";
  return null;
}

/** Detect the clinical priority of a follow-up action, or `null`. */
export function detectPriority(text: string): Priority | null {
  if (!text) return null;
  const clean = stripMarkdown(text);
  if (PRIORITY_URGENT.test(clean)) return "urgent";
  if (PRIORITY_IMPORTANT.test(clean)) return "important";
  if (PRIORITY_ROUTINE.test(clean)) return "routine";
  return null;
}

/**
 * Parse "from **X** (unit) … to **Y** (unit)" lab deltas out of prose. Tolerates
 * `**bold**`, units (mg/dL, %, mmol/L), and a short parenthetical (e.g. a date)
 * between the two values. Returns one entry per match; empty when none.
 */
export function detectLabDeltas(text: string): LabDelta[] {
  if (!text) return [];
  const re =
    /\bfrom\s+\*{0,2}(\d+(?:\.\d+)?)\s*([a-zA-Z%][a-zA-Z%/]*)?\*{0,2}[\s\S]{0,60}?\bto\s+\*{0,2}(\d+(?:\.\d+)?)\s*([a-zA-Z%][a-zA-Z%/]*)?\*{0,2}/gi;
  const deltas: LabDelta[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const from = m[1];
    const to = m[3];
    const unit = (m[4] || m[2] || "").trim() || undefined;
    const dir: "up" | "down" = parseFloat(to) >= parseFloat(from) ? "up" : "down";
    deltas.push({ from, to, unit, dir });
  }
  return deltas;
}

/**
 * Derive a single overall risk level for the report banner. Scans the Risk and
 * Active Conditions sections; returns the strongest severity found, or `null`
 * when nothing detectable (the banner is then omitted — never a false "Low").
 */
export function deriveRiskLevel(sections: InsightSection[]): Severity | null {
  const text = sections
    .filter((s) => s.key === "risk" || s.key === "conditions")
    .map((s) => stripMarkdown(s.body))
    .join(" \n");
  if (!text.trim()) return null;
  if (SEVERITY_HIGH.test(text)) return "high";
  if (SEVERITY_MODERATE.test(text)) return "moderate";
  if (SEVERITY_LOW.test(text)) return "low";
  return null;
}

/** Count paragraph blocks per key for the at-a-glance KPI strip (0 if absent). */
function blockCount(sections: InsightSection[], key: string): number {
  const s = sections.find((x) => x.key === key);
  return s ? splitBlocks(s.body).length : 0;
}

/** Build the four KPI counts (conditions / labs / risks / follow-ups). */
export function deriveKpis(sections: InsightSection[]): InsightKpis {
  return {
    conditions: blockCount(sections, "conditions"),
    labs: blockCount(sections, "labs"),
    risks: blockCount(sections, "risk"),
    followUps: blockCount(sections, "follow_up"),
  };
}
