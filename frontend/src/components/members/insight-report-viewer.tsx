import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import type { VerificationResult } from "@/lib/types/message";
import { ArrowLeft, Download, Brain, ClipboardList } from "lucide-react";

/* ── Shared markdown parsing ── */

interface InsightSection {
  title: string;
  body: string;
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
    if (title && body) sections.push({ title, body });
  }
  if (sections.length === 0) sections.push({ title: "Health Insights", body: markdown });
  return sections;
}

const SECTION_COLORS: Record<string, string> = {
  "health overview": "#3B82F6",
  "active conditions": "#EF4444",
  "lab trends": "#10B981",
  "risk assessment": "#F59E0B",
  recommendations: "#06B6D4",
  "follow-up": "#EC4899",
  hx: "#3B82F6",
  "c/o": "#EF4444",
  ix: "#10B981",
  rx: "#F59E0B",
  q: "#8B5CF6",
};

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, j) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return (
        <strong key={j} className="font-semibold text-gray-900">
          {part.slice(2, -2)}
        </strong>
      );
    if (part.startsWith("*") && part.endsWith("*") && !part.startsWith("**"))
      return (
        <em key={j} className="italic text-gray-700">
          {part.slice(1, -1)}
        </em>
      );
    return <span key={j}>{part}</span>;
  });
}

function renderBody(text: string) {
  const rawLines = text.split("\n").map((l) => l.trim());
  const paragraphs: string[] = [];
  let current = "";
  for (const line of rawLines) {
    const cleaned = line
      .replace(/^[-*•]\s+/, "")
      .replace(/^\d+\.\s+/, "")
      .trim();
    if (!cleaned) {
      if (current.trim()) {
        paragraphs.push(current.trim());
        current = "";
      }
    } else current += (current ? " " : "") + cleaned;
  }
  if (current.trim()) paragraphs.push(current.trim());
  if (paragraphs.length === 0) return null;
  return (
    <div className="space-y-3.5">
      {paragraphs.map((para, i) => (
        <p key={i} className="text-[14px] leading-[1.8] text-gray-800">
          {renderInline(para)}
        </p>
      ))}
    </div>
  );
}

function renderNoteBody(text: string, { checkable = false }: { checkable?: boolean } = {}) {
  return text.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return null;
    if (trimmed.match(/\[ \]/)) {
      return (
        <div key={i} className="flex items-start gap-1.5">
          <span className="text-teal-500 text-xs leading-snug shrink-0">☐</span>
          <span className="text-xs leading-snug text-gray-700">
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
      <p key={i} className="text-xs leading-snug text-gray-700">
        {renderInline(trimmed)}
      </p>
    );
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
          <span className="text-xs font-medium text-gray-400 shrink-0">{number}</span>
        ) : (
          <span className="text-teal-400 text-xs mt-px shrink-0">•</span>
        )}
        <span className="text-xs leading-snug text-gray-700">{children}</span>
      </div>
    );
  }
  const [checked, setChecked] = useState(defaultChecked);
  return (
    <label className="flex items-start gap-2 cursor-pointer group">
      <input
        type="checkbox"
        checked={checked}
        onChange={() => setChecked(!checked)}
        className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
      />
      <span
        className={`text-xs leading-snug ${checked ? "line-through text-gray-400" : "text-gray-700"}`}
      >
        {children}
      </span>
    </label>
  );
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
}: {
  response: string;
  provider: string;
  generatedAt: string;
  verification?: VerificationResult | null;
  memberName: string;
  memberDob: string;
  memberGender: string;
  onBack: () => void;
}) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  const sections = parseSections(response);
  const genDate = new Date(generatedAt);
  const dateStr = genDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const reportId = `DSR-${genDate.getFullYear()}${String(genDate.getMonth() + 1).padStart(2, "0")}${String(genDate.getDate()).padStart(2, "0")}-${String(genDate.getHours()).padStart(2, "0")}${String(genDate.getMinutes()).padStart(2, "0")}`;

  return (
    <div className="min-h-screen bg-white">
      <div className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur-sm print:hidden">
        <div className="max-w-[900px] mx-auto flex items-center justify-between px-10 h-11">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </button>
          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" onClick={() => window.print()} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Export PDF
            </Button>
            <span className="text-[11px] font-mono text-gray-400">{reportId}</span>
          </div>
        </div>
      </div>
      <article className="max-w-[900px] mx-auto px-10 py-8 text-gray-800">
        <header className="mb-6 pb-5 border-b-2 border-gray-900">
          <div className="flex items-center gap-2 mb-3">
            <div className="h-7 w-7 rounded-md bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) flex items-center justify-center">
              <Brain className="h-4 w-4 text-white" />
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-(--brand-accent)">
              DAWNSTAR Family Health Keeper
            </p>
          </div>
          <h1 className="text-2xl font-bold leading-tight tracking-tight text-gray-900">
            Comprehensive Health Assessment Report
          </h1>
          <div className="mt-2 flex items-center gap-2 text-[13px] text-gray-500">
            <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
              AI-Generated
            </span>
            <span className="text-gray-300">|</span>
            <span>{dateStr}</span>
          </div>
        </header>
        <div className="grid grid-cols-2 gap-x-10 mb-5 text-[13px]">
          <div>
            <table className="w-full">
              <tbody>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider w-20">
                    Patient
                  </td>
                  <td className="py-0.5 text-gray-900 font-semibold">{memberName}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider">DOB</td>
                  <td className="py-0.5 text-gray-800">{memberDob}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider">
                    Gender
                  </td>
                  <td className="py-0.5 text-gray-800">{memberGender}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <table className="w-full">
              <tbody>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider w-20">
                    Report ID
                  </td>
                  <td className="py-0.5 text-gray-800 font-mono text-xs">{reportId}</td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider">
                    AI Model
                  </td>
                  <td className="py-0.5 text-gray-800">
                    {provider}
                    {verification && (
                      <span className="ml-2">
                        <VerificationBadge verification={verification} />
                      </span>
                    )}
                  </td>
                </tr>
                <tr>
                  <td className="py-0.5 text-gray-500 text-[11px] uppercase tracking-wider">
                    Generated
                  </td>
                  <td className="py-0.5 text-gray-800">{dateStr}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div className="mb-5 pb-4 border-b border-gray-200">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-900 mb-1.5">
            Abstract
          </h2>
          <p className="text-[13px] leading-[1.65] text-gray-600 italic">
            This report presents an AI-driven health assessment for {memberName}, analyzing{" "}
            {sections.length} clinical domains:{" "}
            {sections.map((s) => s.title.toLowerCase()).join(", ")}. The analysis is based on
            available medical records and should be reviewed by a qualified healthcare professional.
          </p>
        </div>
        <div className="mb-5 pb-4 border-b border-gray-200">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-900 mb-1.5">
            Table of Contents
          </h2>
          <div className="grid grid-cols-2 gap-x-10 gap-y-1.5">
            {sections.map((section, i) => {
              const key = section.title.toLowerCase();
              const color =
                SECTION_COLORS[Object.keys(SECTION_COLORS).find((k) => key.includes(k)) || ""] ||
                "#6B7280";
              return (
                <a
                  key={i}
                  href={`#s${i + 1}`}
                  className="flex items-center gap-2 text-[13px] text-gray-600 hover:text-gray-900 transition-colors group"
                >
                  <span
                    className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                    style={{ backgroundColor: color }}
                  >
                    {i + 1}
                  </span>
                  <span className="group-hover:underline">{section.title}</span>
                </a>
              );
            })}
          </div>
        </div>
        <div className="space-y-7">
          {sections.map((section, i) => {
            const key = section.title.toLowerCase();
            const color =
              SECTION_COLORS[Object.keys(SECTION_COLORS).find((k) => key.includes(k)) || ""] ||
              "#6B7280";
            return (
              <section
                key={i}
                id={`s${i + 1}`}
                className="relative pl-5 border-l-[3px] rounded-sm py-1"
                style={{ borderColor: color }}
              >
                <h2 className="text-[14px] font-bold text-gray-900 mb-2 flex items-center gap-2.5">
                  <span
                    className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                    style={{ backgroundColor: color }}
                  >
                    {i + 1}
                  </span>
                  <span>{section.title}</span>
                </h2>
                {renderBody(section.body)}
              </section>
            );
          })}
        </div>
        <div className="mt-6 pt-3 border-t-2 border-gray-900">
          <p className="text-[12px] leading-relaxed text-gray-500 mb-2">
            <strong className="text-gray-700">Disclaimer.</strong> This report is AI-generated for
            informational purposes only and does not constitute medical advice, diagnosis, or
            treatment recommendations.
          </p>
          <div className="flex items-center justify-between text-[11px] text-gray-400">
            <span>DAWNSTAR Family Health Keeper</span>
            <span>
              {provider} &middot; {dateStr}
            </span>
          </div>
        </div>
      </article>
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
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  const sections = parseSections(response);
  const dateStr = new Date(generatedAt).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="min-h-screen bg-white">
      <div className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur-sm print:hidden">
        <div className="max-w-[640px] mx-auto flex items-center justify-between px-6 h-10">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </button>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={onExportPDF} className="gap-1 h-7 text-xs">
              <Download className="h-3 w-3" />
              PDF
            </Button>
            {verification && <VerificationBadge verification={verification} />}
          </div>
        </div>
      </div>
      <article className="max-w-[640px] mx-auto px-6 py-4">
        <header className="mb-3 pb-2 border-b border-gray-200">
          <div className="flex items-center gap-1.5 mb-1">
            <ClipboardList className="h-4 w-4 text-teal-600" />
            <h1 className="text-sm font-bold text-gray-900">Pre-Consultation Note</h1>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-gray-400">
            <span className="font-medium text-gray-600">{memberName}</span>
            <span>·</span>
            <span>{dateStr}</span>
            <span>·</span>
            <span>{provider}</span>
          </div>
        </header>
        <div className="space-y-2.5">
          {sections.map((section, i) => {
            const isQSection = /q\s*\(|q\s*$|question/i.test(section.title.toLowerCase());
            return (
              <div key={i} className="pl-3 border-l-2 border-teal-300">
                <h2 className="text-xs font-bold text-teal-800 mb-0.5">{section.title}</h2>
                {renderNoteBody(section.body, { checkable: isQSection })}
              </div>
            );
          })}
        </div>
        <div className="mt-4 pt-2 border-t border-gray-100 text-[10px] text-gray-300">
          AI-generated · Review with your doctor
        </div>
      </article>
    </div>
  );
}
