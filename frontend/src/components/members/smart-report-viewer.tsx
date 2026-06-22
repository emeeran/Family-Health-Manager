import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { ArrowLeft, Download, FileHeart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { SystemStatusGrid } from "@/components/members/reports/system-status-grid";
import { ParameterTable } from "@/components/members/reports/parameter-table";
import { FocusCard } from "@/components/members/reports/focus-card";
import { RecommendationList } from "@/components/members/reports/recommendation-list";
import { InsightReport } from "@/components/members/insight-report-viewer";
import { exportElementToPDF } from "@/lib/pdf-export";
import type { VerificationResult } from "@/lib/types/message";
import type { SmartReportData } from "@/lib/types/smart-report";

/**
 * Client-side fallback parser. The backend ships a parsed `report` object,
 * so this only runs for the streamed-token preview path or a legacy payload.
 */
function tryParseSmartReport(response?: string | null): SmartReportData | null {
  if (!response) return null;
  try {
    const cleaned = response
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/\s*```\s*$/i, "")
      .trim();
    const parsed = JSON.parse(cleaned);
    if (parsed && (parsed.systems_at_a_glance || parsed.organ_details)) {
      return parsed as SmartReportData;
    }
  } catch {
    /* not JSON — caller falls back to prose */
  }
  return null;
}

/** Apollo-style section: an uppercase, underlined eyebrow + body. */
function ReportSection({ eyebrow, children }: { eyebrow: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 border-b border-gray-300 pb-1 text-[12px] font-semibold uppercase tracking-[0.1em] text-gray-900">
        {eyebrow}
      </h2>
      {children}
    </section>
  );
}

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
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-[14px] text-gray-900 ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}

interface SmartReportViewerProps {
  response: string;
  provider: string;
  generatedAt: string;
  verification: VerificationResult | null;
  memberName: string;
  onBack: () => void;
  report?: SmartReportData | null;
  rawResponse?: string | null;
}

export function SmartReportViewer({
  response,
  provider,
  generatedAt,
  verification,
  memberName,
  onBack,
  report,
  rawResponse,
}: SmartReportViewerProps) {
  const articleRef = useRef<HTMLDivElement>(null);
  const parsed = useMemo(
    () => tryParseSmartReport(rawResponse ?? response),
    [rawResponse, response]
  );
  const reportData = report ?? parsed;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);

  async function handleExportPDF() {
    if (!articleRef.current) return;
    try {
      await exportElementToPDF(articleRef.current, `smart-report-${memberName}`);
    } catch {
      window.print();
    }
  }

  // No structured data — degrade gracefully to the prose insight report.
  if (!reportData) {
    return (
      <InsightReport
        response={response}
        provider={provider}
        generatedAt={generatedAt}
        verification={verification}
        memberName={memberName}
        memberDob=""
        memberGender=""
        onBack={onBack}
      />
    );
  }

  const systems = reportData.systems_at_a_glance ?? [];
  const attention = systems.filter((s) => s.status === "needs_attention").length;
  const focus = reportData.parameters_in_focus ?? [];
  const details = (reportData.organ_details ?? []).filter(
    (d) => d.parameters && d.parameters.length > 0
  );
  const recs = reportData.recommendations ?? [];

  const allParams = (reportData.organ_details ?? []).flatMap((d) => d.parameters ?? []);
  const outOfRange = allParams.filter(
    (p) => p.status === "out_of_range" || p.status === "critical"
  ).length;
  const borderline = allParams.filter((p) => p.status === "borderline").length;
  const inRange = allParams.filter((p) => p.status === "in_range").length;
  const improved = allParams.filter((p) => p.trend === "improved").length;
  const paramTotal = allParams.length;

  const genDate = new Date(generatedAt);
  const dateStr = genDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const pad = (n: number) => String(n).padStart(2, "0");
  const reportId = `SR-${genDate.getFullYear()}${pad(genDate.getMonth() + 1)}${pad(genDate.getDate())}-${pad(genDate.getHours())}${pad(genDate.getMinutes())}`;

  const intro =
    paramTotal === 0
      ? `Here's an updated Smart Health Report based on ${memberName}'s recorded clinical data. Add lab results to unlock a detailed parameter breakdown.`
      : `Here's an updated Smart Health Report based on ${memberName}'s recorded lab results and clinical data. ${
          outOfRange > 0
            ? `${outOfRange} of ${paramTotal} parameters currently fall outside the healthy range${
                attention > 0
                  ? `, across ${attention} body system${attention > 1 ? "s" : ""} that need attention`
                  : ""
              }.`
            : `All ${paramTotal} parameters are within the healthy range.`
        }${improved > 0 ? ` ${improved} parameter${improved > 1 ? "s have" : " has"} improved since the previous report.` : ""}`;

  return (
    <div className="min-h-screen bg-background">
      {/* Slim sticky command bar (theme-aware; sits off the document) */}
      <div className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-sm print:hidden">
        <div className="mx-auto flex h-10 max-w-[900px] items-center justify-between gap-2 px-3">
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
            <span className="truncate text-[13px] font-semibold text-foreground">Smart Report</span>
            <VerificationBadge verification={verification} />
          </div>
          <Button variant="outline" size="sm" className="h-7" onClick={handleExportPDF}>
            <Download className="h-3.5 w-3.5" />
            PDF
          </Button>
        </div>
      </div>

      <div className="mx-auto max-w-[900px] px-3 py-6">
        {/* The document page — fixed light (PDF-like) regardless of app theme */}
        <article
          ref={articleRef}
          className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
        >
          {/* Cover */}
          <header className="bg-[#FFF8F0] px-6 py-6 sm:px-8">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#FF5722]">
                  DAWNSTAR · Smart Report
                </p>
                <h1 className="mt-2 text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
                  Smart Health Report
                </h1>
                <p className="mt-1 text-sm text-gray-500">
                  Helping you understand your health better
                </p>
              </div>
              <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#E3F2FD] sm:flex">
                <FileHeart className="h-6 w-6 text-[#FF5722]" />
              </div>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
              <MetaItem label="Curated for" value={memberName} />
              <MetaItem label="Curated date" value={dateStr} />
              <MetaItem label="Report ID" value={reportId} mono />
            </div>
          </header>

          {/* Body */}
          <div className="space-y-7 px-6 py-6 sm:px-8">
            <ReportSection eyebrow="Overall health summary">
              <p className="text-[13px] leading-relaxed text-gray-700">{intro}</p>
              {paramTotal > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
                  {outOfRange > 0 && (
                    <span>
                      <span className="text-red-500">●</span> {outOfRange} out of range
                    </span>
                  )}
                  {borderline > 0 && (
                    <span>
                      <span className="text-amber-500">●</span> {borderline} borderline
                    </span>
                  )}
                  {inRange > 0 && <span className="text-emerald-600">✓ {inRange} in range</span>}
                </div>
              )}
            </ReportSection>

            {systems.length > 0 && (
              <ReportSection eyebrow="Your body systems">
                <SystemStatusGrid systems={systems} />
              </ReportSection>
            )}

            {details.length > 0 && (
              <ReportSection eyebrow="Parameters in detail">
                <div className="space-y-3">
                  {details.map((d, i) => (
                    <ParameterTable key={i} detail={d} />
                  ))}
                </div>
              </ReportSection>
            )}

            {focus.length > 0 && (
              <ReportSection eyebrow="Key findings">
                <div className="space-y-2.5">
                  {focus.map((p, i) => (
                    <FocusCard key={i} param={p} />
                  ))}
                </div>
              </ReportSection>
            )}

            {recs.length > 0 && (
              <ReportSection eyebrow="Next steps">
                <p className="mb-3 text-[13px] font-medium text-gray-700">
                  Here are a few Next Steps for you:
                </p>
                <RecommendationList recs={recs} />
              </ReportSection>
            )}

            <div className="rounded-lg bg-gray-50 p-3 text-[12px] leading-relaxed text-gray-500">
              <span className="font-semibold text-gray-600">NOTE:</span> This information is for
              educational purposes only. Please consult your doctor for personalised advice.
            </div>
          </div>

          {/* Footer */}
          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 px-6 py-3 text-[11px] text-gray-500 sm:px-8">
            <span className="font-semibold uppercase tracking-wide">SMART REPORT</span>
            <span>
              {memberName} · {dateStr}
            </span>
          </footer>
        </article>
      </div>
    </div>
  );
}
