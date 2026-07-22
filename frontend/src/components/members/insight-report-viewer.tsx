import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { InsightSectionBlock } from "@/components/members/reports/insight-section";
import { StreamingPreview } from "@/components/members/reports/streaming-preview";
import { ValidationFootnote } from "@/components/members/reports/validation-footnote";
import { Hba1cTrendChart } from "@/components/members/reports/hba1c-trend-chart";
import { exportElementToPDF } from "@/lib/pdf-export";
import { parseSections, sectionKey } from "@/lib/parse-sections";
import type { InsightSection } from "@/lib/parse-sections";
import { getHba1cHistory } from "@/lib/api/members";
import type { Hba1cHistoryEntry } from "@/lib/types/member";
import { deriveKpis, deriveRiskLevel, type Severity } from "@/lib/insight-extract";
import type { VerificationResult } from "@/lib/types/message";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Download,
  Brain,
  ClipboardList,
  AlertTriangle,
  ShieldAlert,
  ShieldCheck,
  Activity,
  FlaskConical,
  CalendarClock,
  Loader2,
  RefreshCw,
} from "lucide-react";

// Re-exported for legacy callers (overview-tab, ai-assistant-tab inline PDFs).
export { parseSections };
export type { InsightSection };

const NOTE_ACCENT: Record<string, string> = {
  hx: "var(--chart-1)",
  "c/o": "var(--destructive)",
  ix: "var(--chart-2)",
  rx: "var(--chart-3)",
  q: "#8b5cf6",
};

/* ── Pre-consultation note rendering (line-by-line, checkable Q-section) ── */

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, j) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={j} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && !part.startsWith("**")) {
      return (
        <em key={j} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <span key={j}>{part}</span>;
  });
}

function CheckableLine({
  checkable,
  defaultChecked,
  number,
  children,
}: {
  checkable: boolean;
  defaultChecked: boolean;
  number?: string;
  children: React.ReactNode;
}) {
  if (!checkable) {
    return (
      <div className="flex items-start gap-1.5">
        {number ? (
          <span className="shrink-0 text-xs font-medium text-muted-foreground">{number}</span>
        ) : (
          <span className="mt-px shrink-0 text-xs text-teal-500">•</span>
        )}
        <span className="text-xs leading-snug text-foreground/80">{children}</span>
      </div>
    );
  }
  const [checked, setChecked] = useState(defaultChecked);
  return (
    <label className="group flex cursor-pointer items-start gap-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={() => setChecked(!checked)}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-border text-teal-600 focus:ring-teal-500"
      />
      <span
        className={`text-xs leading-snug ${checked ? "text-muted-foreground line-through" : "text-foreground/80"}`}
      >
        {children}
      </span>
    </label>
  );
}

function renderNoteBody(text: string, { checkable = false }: { checkable?: boolean } = {}) {
  return text.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return null;
    if (trimmed.match(/\[ \]/)) {
      return (
        <div key={i} className="flex items-start gap-1.5">
          <span className="shrink-0 text-xs leading-snug text-teal-500">☐</span>
          <span className="text-xs leading-snug text-foreground/80">
            {renderInline(trimmed.replace(/^[-*]\s*/, "").replace(/\[ \]\s*/, ""))}
          </span>
        </div>
      );
    }
    if (/^[-*•]\s/.test(trimmed)) {
      return (
        <CheckableLine key={i} checkable={checkable} defaultChecked={false}>
          {renderInline(trimmed.replace(/^[-*•]\s+/, ""))}
        </CheckableLine>
      );
    }
    if (/^\d+\.\s/.test(trimmed)) {
      const match = trimmed.match(/^(\d+\.)\s*(.*)/);
      if (match) {
        return (
          <CheckableLine key={i} checkable={checkable} defaultChecked={false} number={match[1]}>
            {renderInline(match[2])}
          </CheckableLine>
        );
      }
    }
    return (
      <p key={i} className="text-xs leading-snug text-foreground/80">
        {renderInline(trimmed)}
      </p>
    );
  });
}

/* ── InsightReport: editorial clinical document ── */

const KEY_ACCENT: Record<string, string> = {
  overview: "#5b7fff",
  conditions: "#dc2626",
  labs: "#4ade80",
  risk: "#fb923c",
  recommendations: "#06b6d4",
  follow_up: "#ec4899",
  other: "#737373",
};

function MetaItem({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 truncate text-[13px] font-medium text-gray-800",
          mono && "font-mono text-gray-600"
        )}
      >
        {value}
      </div>
    </div>
  );
}

function KpiStrip({ kpis }: { kpis: ReturnType<typeof deriveKpis> }) {
  const items = [
    { n: kpis.conditions, label: "Active conditions", accent: "#dc2626", Icon: Activity },
    { n: kpis.labs, label: "Lab findings", accent: "#4ade80", Icon: FlaskConical },
    { n: kpis.risks, label: "Risks flagged", accent: "#fb923c", Icon: ShieldAlert },
    { n: kpis.followUps, label: "Follow-ups", accent: "#ec4899", Icon: CalendarClock },
  ];
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {items.map((it, i) => (
        <div
          key={i}
          className="rounded-xl border border-gray-200 bg-gradient-to-b from-white to-gray-50/70 p-3.5 transition-colors hover:border-gray-300"
        >
          <div className="flex items-center justify-between gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400">
              {it.label}
            </span>
            <it.Icon className="h-3.5 w-3.5" style={{ color: it.accent }} />
          </div>
          <div
            className="mt-2 text-[26px] font-bold leading-none tabular-nums"
            style={{ color: it.accent }}
          >
            {it.n}
          </div>
        </div>
      ))}
    </div>
  );
}

const RISK_STYLE: Record<
  Severity,
  {
    wrap: string;
    badge: string;
    Icon: typeof AlertTriangle;
    textCls: string;
    label: string;
  }
> = {
  high: {
    wrap: "border-red-200 bg-gradient-to-r from-red-50 to-red-50/20",
    badge: "bg-red-100 text-red-600 ring-red-200",
    Icon: AlertTriangle,
    textCls: "text-red-900",
    label: "High overall risk",
  },
  moderate: {
    wrap: "border-amber-200 bg-gradient-to-r from-amber-50 to-amber-50/20",
    badge: "bg-amber-100 text-amber-600 ring-amber-200",
    Icon: ShieldAlert,
    textCls: "text-amber-900",
    label: "Moderate overall risk",
  },
  low: {
    wrap: "border-emerald-200 bg-gradient-to-r from-emerald-50 to-emerald-50/20",
    badge: "bg-emerald-100 text-emerald-600 ring-emerald-200",
    Icon: ShieldCheck,
    textCls: "text-emerald-900",
    label: "Low overall risk",
  },
};

function RiskBanner({ level }: { level: Severity }) {
  const s = RISK_STYLE[level];
  const Icon = s.Icon;
  return (
    <div className={cn("flex items-center gap-3 rounded-xl border px-4 py-3", s.wrap)}>
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-1",
          s.badge
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className={cn("text-[13px] font-bold leading-tight", s.textCls)}>{s.label}</div>
        <div className="text-[11px] text-gray-500">
          Derived from your risk &amp; active-condition assessments
        </div>
      </div>
    </div>
  );
}

function SectionNav({ sections }: { sections: InsightSection[] }) {
  if (sections.length < 2) return null;
  const scrollTo = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <nav className="flex flex-wrap gap-1.5">
      {sections.map((s, i) => {
        const id = `insight-sec-${i}`;
        const accent = KEY_ACCENT[s.key ?? "other"] ?? "var(--muted-foreground)";
        return (
          <a
            key={id}
            href={`#${id}`}
            onClick={(e) => scrollTo(e, id)}
            className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 transition-colors hover:border-gray-300 hover:text-gray-900"
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent }} />
            {s.title}
          </a>
        );
      })}
    </nav>
  );
}

export function InsightReport({
  response,
  provider,
  generatedAt,
  verification,
  memberName,
  memberDob,
  memberGender,
  memberId,
  onBack,
  sections: sectionsProp,
  onRegenerate,
  regenerating,
  regenerateStage,
  regenerateText,
  onCancelRegenerate,
}: {
  response: string;
  provider: string;
  generatedAt: string;
  verification?: VerificationResult | null;
  memberName: string;
  memberDob: string;
  memberGender: string;
  /** Used to fetch the real HbA1c trend series for the chart. */
  memberId?: string;
  onBack: () => void;
  /** Server-parsed sections (preferred); falls back to client-side parseSections. */
  sections?: InsightSection[] | null;
  /** When provided, a Regenerate button is shown in the command bar. */
  onRegenerate?: () => void;
  /** True while regeneration is streaming; shows an inline progress panel. */
  regenerating?: boolean;
  /** Stage label for the in-flight regeneration. */
  regenerateStage?: string;
  /** Tokens streamed so far during regeneration. */
  regenerateText?: string;
  /** Abort an in-flight regeneration. */
  onCancelRegenerate?: () => void;
}) {
  const articleRef = useRef<HTMLDivElement>(null);
  const sections = sectionsProp ?? parseSections(response);
  const kpis = deriveKpis(sections);
  const riskLevel = deriveRiskLevel(sections);
  const [hba1c, setHba1c] = useState<Hba1cHistoryEntry[] | null>(null);

  useEffect(() => {
    if (!memberId) return;
    let alive = true;
    getHba1cHistory(memberId)
      .then((d) => {
        if (alive) setHba1c(d);
      })
      .catch(() => {
        if (alive) setHba1c(null);
      });
    return () => {
      alive = false;
    };
  }, [memberId]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  async function handleExportPDF() {
    if (!articleRef.current) return;
    try {
      await exportElementToPDF(articleRef.current, `health-assessment-${memberName}`);
    } catch {
      window.print();
    }
  }

  const genDate = new Date(generatedAt);
  const dateStr = genDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const pad = (n: number) => String(n).padStart(2, "0");
  const reportId = `HA-${genDate.getFullYear()}${pad(genDate.getMonth() + 1)}${pad(genDate.getDate())}-${pad(genDate.getHours())}${pad(genDate.getMinutes())}`;

  return (
    <div className="min-h-screen bg-background">
      {/* Slim sticky command bar (theme-aware; sits off the document) */}
      <div className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-sm print:hidden">
        <div className="mx-auto flex h-10 max-w-[820px] items-center justify-between gap-2 px-3">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={onBack}
              aria-label="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <span className="truncate text-[13px] font-semibold text-foreground">
              Health Assessment
            </span>
            <VerificationBadge verification={verification} />
          </div>
          <div className="flex items-center gap-2">
            {onRegenerate && (
              <Button
                variant="outline"
                size="sm"
                className="h-7"
                onClick={onRegenerate}
                disabled={regenerating}
              >
                {regenerating ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                {regenerating ? "Analyzing..." : "Regenerate"}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="h-7"
              onClick={handleExportPDF}
              disabled={regenerating}
              title={regenerating ? "Finish regenerating first" : "Export to PDF"}
            >
              <Download className="h-3.5 w-3.5" />
              PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[820px] px-3 py-6">
        {/* Inline regeneration progress — streams live over the stale report */}
        {regenerating && (
          <div className="mb-4 rounded-xl border border-(--brand-accent)/30 bg-muted/30 p-4 print:hidden">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-(--brand-accent)" />
                <span className="truncate text-sm font-medium text-(--brand-accent)">
                  {regenerateStage || "Analyzing records..."}
                </span>
              </div>
              {onCancelRegenerate && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 shrink-0 text-xs text-muted-foreground"
                  onClick={onCancelRegenerate}
                >
                  Cancel
                </Button>
              )}
            </div>
            {regenerateText && (
              <div className="mt-2">
                <StreamingPreview text={regenerateText} stage={regenerateStage} />
              </div>
            )}
          </div>
        )}

        {/* Sticky section nav (under the command bar) */}
        {sections.length > 1 && (
          <div className="sticky top-10 z-10 -mx-3 mb-4 border-b border-border bg-background/95 px-3 py-2 backdrop-blur-sm print:hidden">
            <SectionNav sections={sections} />
          </div>
        )}

        {/* The document page — fixed light (PDF-like) regardless of app theme */}
        <article
          ref={articleRef}
          className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-xl shadow-gray-200/50 ring-1 ring-gray-100"
        >
          {/* Accent top bar */}
          <div className="h-1.5 bg-gradient-to-r from-[#ff6b35] via-[#fb923c] to-[#5b7fff]" />
          {/* Header */}
          <header className="px-6 py-7 sm:px-9">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#ff6b35]">
                  <Brain className="h-3.5 w-3.5" />
                  AI Health Assessment
                </div>
                <h1 className="mt-2 text-2xl font-bold leading-tight tracking-tight text-gray-900 sm:text-[28px]">
                  Health Assessment Report
                </h1>
                <p className="mt-1.5 text-[13px] text-gray-500">
                  Comprehensive clinical review of your recorded health data
                </p>
              </div>
              <div className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-50 to-amber-50 ring-1 ring-orange-100 sm:flex">
                <Brain className="h-7 w-7 text-[#ff6b35]" />
              </div>
            </div>
            {(provider || verification) && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {provider && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600">
                    <Brain className="h-3 w-3 text-[#ff6b35]" />
                    Generated via {provider}
                  </span>
                )}
                <VerificationBadge verification={verification} />
              </div>
            )}
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-gray-100 pt-5 sm:grid-cols-3 lg:grid-cols-5">
              <MetaItem label="Patient" value={memberName} />
              <MetaItem label="Date of birth" value={memberDob || "—"} />
              <MetaItem
                label="Gender"
                value={
                  memberGender ? memberGender.charAt(0).toUpperCase() + memberGender.slice(1) : "—"
                }
              />
              <MetaItem label="Curated" value={dateStr} />
              <MetaItem label="Report ID" value={reportId} mono />
            </div>
          </header>

          {/* Body */}
          <div className="space-y-6 px-6 py-7 sm:px-9">
            <KpiStrip kpis={kpis} />
            {riskLevel && <RiskBanner level={riskLevel} />}
            {hba1c && hba1c.length >= 2 && <Hba1cTrendChart data={hba1c} />}

            <div className="space-y-8">
              {sections.map((s, i) => (
                <InsightSectionBlock key={i} section={s} id={`insight-sec-${i}`} index={i + 1} />
              ))}
            </div>

            <ValidationFootnote
              provider={provider}
              verification={verification ?? null}
              generatedAt={generatedAt}
            />
          </div>

          {/* Footer */}
          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 px-6 py-3 text-[11px] text-gray-500 sm:px-9">
            <span className="font-semibold uppercase tracking-wide">AI HEALTH ASSESSMENT</span>
            <span>
              {memberName} · {dateStr}
            </span>
          </footer>
        </article>
      </div>
    </div>
  );
}

/* ── PreConsultation Note Viewer ── */

export function PreConsultationNoteViewer({
  response,
  provider,
  generatedAt,
  verification,
  memberName,
  onBack,
  onExportPDF,
}: {
  response: string;
  provider: string;
  generatedAt: string;
  verification?: VerificationResult | null;
  memberName: string;
  onBack: () => void;
  onExportPDF: () => void;
}) {
  const noteRef = useRef<HTMLElement>(null);
  const sections = parseSections(response);
  const dateStr = new Date(generatedAt).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  async function handlePDF() {
    const el = noteRef.current;
    if (!el) {
      onExportPDF();
      return;
    }
    try {
      await exportElementToPDF(el, `pre-consultation-${dateStr}.pdf`);
    } catch {
      onExportPDF();
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-sm print:hidden">
        <div
          className="mx-auto flex h-10 items-center justify-between px-4"
          style={{ maxWidth: 640 }}
        >
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </button>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={handlePDF} className="h-7 gap-1 text-xs">
              <Download className="h-3 w-3" />
              PDF
            </Button>
            {verification && <VerificationBadge verification={verification} />}
          </div>
        </div>
      </div>
      <article ref={noteRef} className="mx-auto px-4 py-4" style={{ maxWidth: 640 }}>
        <header className="mb-3 border-b border-border pb-2">
          <div className="mb-1 flex items-center gap-1.5">
            <ClipboardList className="h-4 w-4 text-teal-600" />
            <h1 className="text-sm font-bold text-foreground">Pre-Consultation Note</h1>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground/80">{memberName}</span>
            <span>·</span>
            <span>{dateStr}</span>
            <span>·</span>
            <span>{provider}</span>
          </div>
        </header>
        <div className="space-y-2.5">
          {sections.map((section, i) => {
            const isQSection = /q\s*\(|q\s*$|question/i.test(section.title.toLowerCase());
            const accent = NOTE_ACCENT[sectionKey(section.title)] || "var(--muted-foreground)";
            return (
              <div
                key={i}
                className="rounded-md border border-border border-l-2 bg-card p-2.5 pl-3"
                style={{ borderLeftColor: accent }}
              >
                <h2 className="mb-1 text-xs font-bold text-foreground">{section.title}</h2>
                <div className="space-y-1">
                  {renderNoteBody(section.body, { checkable: isQSection })}
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 border-t border-border pt-2 text-[10px] text-muted-foreground">
          AI-generated · Review with your doctor
        </div>
      </article>
    </div>
  );
}
