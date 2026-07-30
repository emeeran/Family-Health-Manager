/**
 * Per-key "editorial document" renderer for a parsed insight section.
 *
 * Each key gets a purpose-built layout driven by the pure extractors in
 * `@/lib/insight-extract` (trajectory badges, lab delta chips, severity
 * callouts, priority groups). **Every** branch falls back to clean prose when
 * extraction finds nothing — so a section that lacks the expected cues renders
 * exactly as readable text, never broken.
 *
 * The palette is the fixed-light "document page" look (text-gray-* on white),
 * matching `SmartReportViewer` so the two surfaces read as a deliberate pair.
 */

import type { ReactNode } from "react";
import {
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  Activity,
  HeartPulse,
  FlaskConical,
  Lightbulb,
  CalendarClock,
  FileText,
} from "lucide-react";
import type { InsightSection } from "@/lib/parse-sections";
import {
  splitBlocks,
  detectTrajectory,
  detectSeverity,
  detectPriority,
  detectLabDeltas,
  type Tone,
  type Severity,
  type LabDelta,
} from "@/lib/insight-extract";
import { cn } from "@/lib/utils";

// Fixed hexes (not theme vars) so the forced-light document page looks identical
// in light and dark app themes — same approach SmartReportViewer takes.
const KEY_ACCENT: Record<string, string> = {
  overview: "#5b7fff",
  conditions: "#dc2626",
  labs: "#4ade80",
  risk: "#fb923c",
  recommendations: "#06b6d4",
  follow_up: "#ec4899",
  other: "#737373",
};

// A distinct icon per section type so each block is visually identifiable at a
// glance, rendered inside an accent-tinted chip in the eyebrow.
const KEY_ICON: Record<string, typeof Activity> = {
  overview: Activity,
  conditions: HeartPulse,
  labs: FlaskConical,
  risk: ShieldAlert,
  recommendations: Lightbulb,
  follow_up: CalendarClock,
  other: FileText,
};

const CARD_BASE =
  "rounded-xl border border-gray-200 bg-white p-3.5 shadow-sm transition-shadow hover:shadow-md";

/* ── shared inline + prose helpers (self-contained; no markdown-sections dep) ── */

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-gray-900">
          {tok.slice(2, -2)}
        </strong>
      );
    } else if (tok.startsWith("`")) {
      nodes.push(
        <code
          key={key++}
          className="rounded bg-gray-100 px-1 font-mono text-[0.85em] text-gray-800"
        >
          {tok.slice(1, -1)}
        </code>
      );
    } else {
      nodes.push(<em key={key++}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** Split prose into display paragraphs (blank-line first, else line breaks). */
function toParagraphs(text: string): string[] {
  const blank = text
    .split(/\n{2,}/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (blank.length > 1) return blank;
  return text
    .split(/\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function Prose({ text }: { text: string }) {
  const paras = toParagraphs(text);
  return (
    <div className="space-y-1.5">
      {paras.map((p, i) => (
        <p key={i} className="text-[13px] leading-snug text-gray-700">
          {renderInline(p)}
        </p>
      ))}
    </div>
  );
}

/* ── eyebrow (uppercase, underlined — Apollo-style) ── */

function Eyebrow({
  index,
  title,
  accent,
  Icon,
}: {
  index: number;
  title: string;
  accent: string;
  Icon: typeof Activity;
}) {
  return (
    <div className="mb-4 flex items-center gap-2.5">
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
        style={{ backgroundColor: `${accent}1a` }}
      >
        <Icon className="h-3.5 w-3.5" style={{ color: accent }} />
      </span>
      <h2 className="text-[13px] font-bold uppercase tracking-[0.08em] text-gray-900">{title}</h2>
      <span className="h-px flex-1 bg-gray-200" />
      <span className="text-[11px] font-bold leading-none tabular-nums text-gray-300">
        {String(index).padStart(2, "0")}
      </span>
    </div>
  );
}

/* ── per-key bodies ── */

function OverviewBody({ body }: { body: string }) {
  const paras = toParagraphs(body);
  return (
    <div className="space-y-2">
      {paras.map((p, i) => (
        <p
          key={i}
          className={cn("leading-relaxed text-gray-700", i === 0 ? "text-[15px]" : "text-[13px]")}
        >
          {renderInline(p)}
        </p>
      ))}
    </div>
  );
}

const TRAJ_BADGE: Record<Tone, { cls: string; arrow: string }> = {
  good: { cls: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200", arrow: "↑" },
  warn: { cls: "bg-amber-50 text-amber-700 ring-1 ring-amber-200", arrow: "→" },
  bad: { cls: "bg-red-50 text-red-700 ring-1 ring-red-200", arrow: "↓" },
};

function ConditionsBody({ body }: { body: string }) {
  const blocks = splitBlocks(body);
  if (blocks.length === 0) return <Prose text={body} />;
  const annotated = blocks.map((b) => ({ b, t: detectTrajectory(b) }));
  // Only enhance when at least one block yields a cue; else clean prose.
  if (!annotated.some((x) => x.t)) return <Prose text={body} />;
  return (
    <div className="space-y-2">
      {annotated.map(({ b, t }, i) => (
        <div key={i} className={cn("flex items-start gap-3", CARD_BASE)}>
          <div className="min-w-0 flex-1 space-y-1.5">
            {toParagraphs(b).map((p, j) => (
              <p key={j} className="text-[13px] leading-snug text-gray-700">
                {renderInline(p)}
              </p>
            ))}
          </div>
          {t && (
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                TRAJ_BADGE[t.tone].cls
              )}
            >
              {TRAJ_BADGE[t.tone].arrow} {t.label}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function DeltaChip({ d }: { d: LabDelta }) {
  const up = d.dir === "up";
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-gray-50 px-2 py-0.5 text-[11px] font-medium text-gray-700 ring-1 ring-gray-200">
      <span className={up ? "text-sky-600" : "text-slate-500"}>{up ? "▲" : "▼"}</span>
      {d.from}→{d.to}
      {d.unit ? ` ${d.unit}` : ""}
    </span>
  );
}

function LabsBody({ body }: { body: string }) {
  const blocks = splitBlocks(body);
  if (blocks.length === 0) return <Prose text={body} />;
  const annotated = blocks.map((b) => ({ b, deltas: detectLabDeltas(b) }));
  if (!annotated.some((x) => x.deltas.length)) return <Prose text={body} />;
  return (
    <div className="space-y-2">
      {annotated.map(({ b, deltas }, i) => (
        <div key={i} className={CARD_BASE}>
          <div className="space-y-1.5">
            {toParagraphs(b).map((p, j) => (
              <p key={j} className="text-[13px] leading-snug text-gray-700">
                {renderInline(p)}
              </p>
            ))}
          </div>
          {deltas.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {deltas.map((d, k) => (
                <DeltaChip key={k} d={d} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

const SEV_STYLE: Record<
  Severity,
  {
    wrap: string;
    border: string;
    iconCls: string;
    badge: string;
    label: string;
    Icon: typeof Activity;
  }
> = {
  high: {
    wrap: "bg-red-50",
    border: "border-l-red-500",
    iconCls: "text-red-600",
    badge: "bg-red-100 text-red-700",
    label: "High",
    Icon: AlertTriangle,
  },
  moderate: {
    wrap: "bg-amber-50",
    border: "border-l-amber-500",
    iconCls: "text-amber-600",
    badge: "bg-amber-100 text-amber-700",
    label: "Moderate",
    Icon: ShieldAlert,
  },
  low: {
    wrap: "bg-emerald-50",
    border: "border-l-emerald-500",
    iconCls: "text-emerald-600",
    badge: "bg-emerald-100 text-emerald-700",
    label: "Low",
    Icon: ShieldCheck,
  },
};

function RiskBody({ body }: { body: string }) {
  const blocks = splitBlocks(body);
  if (blocks.length === 0) return <Prose text={body} />;
  const annotated = blocks.map((b) => ({ b, sev: detectSeverity(b) }));
  if (!annotated.some((x) => x.sev)) return <Prose text={body} />;
  return (
    <div className="space-y-2">
      {annotated.map(({ b, sev }, i) => {
        const style = sev ? SEV_STYLE[sev] : null;
        const Icon = style?.Icon ?? Activity;
        return (
          <div
            key={i}
            className={cn(
              "rounded-xl border border-gray-200 border-l-4 p-3.5 shadow-sm",
              style ? `${style.wrap} ${style.border}` : "bg-white"
            )}
          >
            <div className="flex items-start gap-2">
              <Icon
                className={cn("mt-0.5 h-4 w-4 shrink-0", style ? style.iconCls : "text-gray-400")}
              />
              <div className="min-w-0 flex-1 space-y-1.5">
                {toParagraphs(b).map((p, j) => (
                  <p key={j} className="text-[13px] leading-snug text-gray-700">
                    {renderInline(p)}
                  </p>
                ))}
              </div>
              {style && (
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                    style.badge
                  )}
                >
                  {style.label}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NumberedListBody({ body }: { body: string }) {
  const blocks = splitBlocks(body);
  if (blocks.length === 0) return <Prose text={body} />;
  return (
    <ol className="space-y-2">
      {blocks.map((b, i) => (
        <li key={i} className={cn("flex gap-3", CARD_BASE)}>
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-900 text-[11px] font-bold text-white">
            {i + 1}
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            {toParagraphs(b).map((p, j) => (
              <p key={j} className="text-[13px] leading-snug text-gray-700">
                {renderInline(p)}
              </p>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}

const PRIORITY_STYLE = {
  urgent: { dot: "bg-red-500", label: "Urgent" },
  important: { dot: "bg-amber-500", label: "Important" },
  routine: { dot: "bg-emerald-500", label: "Routine" },
  other: { dot: "bg-gray-400", label: "Also noted" },
} as const;

function FollowUpBody({ body }: { body: string }) {
  const blocks = splitBlocks(body);
  if (blocks.length === 0) return <Prose text={body} />;
  const groups: Record<keyof typeof PRIORITY_STYLE, string[]> = {
    urgent: [],
    important: [],
    routine: [],
    other: [],
  };
  for (const b of blocks) {
    const p = detectPriority(b);
    groups[p ?? "other"].push(b);
  }
  const hasPriority = groups.urgent.length + groups.important.length + groups.routine.length > 0;
  if (!hasPriority) return <NumberedListBody body={body} />;
  const order: (keyof typeof PRIORITY_STYLE)[] = ["urgent", "important", "routine", "other"];
  return (
    <div className="space-y-3">
      {order
        .filter((k) => groups[k].length > 0)
        .map((k) => (
          <div key={k}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className={cn("h-2 w-2 rounded-full", PRIORITY_STYLE[k].dot)} />
              <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                {PRIORITY_STYLE[k].label}
              </span>
            </div>
            <ul className="space-y-1.5">
              {groups[k].map((b, i) => (
                <li key={i} className="flex gap-2 rounded-lg border border-gray-200 bg-white p-3">
                  <span
                    className={cn(
                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                      PRIORITY_STYLE[k].dot
                    )}
                  />
                  <div className="min-w-0 flex-1 space-y-1">
                    {toParagraphs(b).map((p, j) => (
                      <p key={j} className="text-[13px] leading-snug text-gray-700">
                        {renderInline(p)}
                      </p>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

function renderBody(section: InsightSection): ReactNode {
  switch (section.key) {
    case "overview":
      return <OverviewBody body={section.body} />;
    case "conditions":
      return <ConditionsBody body={section.body} />;
    case "labs":
      return <LabsBody body={section.body} />;
    case "risk":
      return <RiskBody body={section.body} />;
    case "recommendations":
      return <NumberedListBody body={section.body} />;
    case "follow_up":
      return <FollowUpBody body={section.body} />;
    default:
      return <Prose text={section.body} />;
  }
}

/**
 * Render one insight section as an editorial block: underlined eyebrow + a
 * key-specific body. `id` anchors the sticky section nav (scroll-mt offsets the
 * sticky bars).
 */
export function InsightSectionBlock({
  section,
  id,
  index = 1,
}: {
  section: InsightSection;
  id?: string;
  index?: number;
}) {
  const key = section.key ?? "other";
  const accent = KEY_ACCENT[key] ?? "#737373";
  const Icon = KEY_ICON[key] ?? FileText;
  return (
    <section id={id} className="scroll-mt-28">
      <Eyebrow index={index} title={section.title} accent={accent} Icon={Icon} />
      {renderBody(section)}
    </section>
  );
}

export { renderInline };
