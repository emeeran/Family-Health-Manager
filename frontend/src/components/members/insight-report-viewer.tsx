import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { ReportShell } from "@/components/members/reports/report-shell";
import { MarkdownSections } from "@/components/members/reports/markdown-sections";
import { exportElementToPDF } from "@/lib/pdf-export";
import { parseSections, sectionKey } from "@/lib/parse-sections";
import type { InsightSection } from "@/lib/parse-sections";
import type { VerificationResult } from "@/lib/types/message";
import { ArrowLeft, Download, Brain, ClipboardList } from "lucide-react";

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

/* ── InsightReport ── */

export function InsightReport({
  response,
  provider,
  generatedAt,
  verification,
  memberName,
  memberDob,
  memberGender,
  onBack,
  sections: sectionsProp,
}: {
  response: string;
  provider: string;
  generatedAt: string;
  verification?: VerificationResult | null;
  memberName: string;
  memberDob: string;
  memberGender: string;
  onBack: () => void;
  /** Server-parsed sections (preferred); falls back to client-side parseSections. */
  sections?: InsightSection[] | null;
}) {
  const articleRef = useRef<HTMLDivElement>(null);
  const sections = sectionsProp ?? parseSections(response);

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

  const meta = [memberDob && `DOB ${memberDob}`, memberGender].filter(Boolean).join(" · ");

  return (
    <ReportShell
      title="Health Assessment"
      memberName={memberName}
      subtitle={meta || undefined}
      generatedAt={generatedAt}
      provider={provider}
      verification={verification}
      onBack={onBack}
      onExportPDF={handleExportPDF}
      maxWidth={900}
    >
      <div ref={articleRef} className="space-y-3">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
          <Brain className="h-3.5 w-3.5" />
          AI Health Assessment
        </div>
        <MarkdownSections sections={sections} variant="report" />
      </div>
    </ReportShell>
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
