import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { SystemStatusGrid } from "@/components/members/reports/system-status-grid";
import { ParameterTable } from "@/components/members/reports/parameter-table";
import { FocusCard } from "@/components/members/reports/focus-card";
import { RecommendationList } from "@/components/members/reports/recommendation-list";
import { ReportFooter } from "@/components/shared/report-footer";
import type { ReportMeta } from "@/lib/types/report-meta";
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

/**
 * Stylized health-dashboard cover graphic, replicating the SmartReport PDF
 * cover: a soft blue panel holding a white bar chart, a green upward trend
 * line, a red heart with a pulse trace, and orange star/cross accents.
 * Inline SVG so it scales crisply and prints/PDF-exports cleanly.
 */
function SmartReportCoverGraphic() {
  return (
    <svg viewBox="0 0 120 120" className="h-24 w-24" role="img" aria-label="Health summary graphic">
      <rect x="6" y="10" width="108" height="102" rx="22" fill="#E3F2FD" />
      {/* orange star accent (top-left) */}
      <path
        d="M28 19l2.3 5 5.5.6-4.1 3.7 1.1 5.4L28 31l-4.8 2.7 1.1-5.4-4.1-3.7 5.5-.6z"
        fill="#FF5722"
      />
      {/* orange medical cross (top-right) */}
      <g fill="#FF5722">
        <rect x="85" y="20" width="15" height="5" rx="2.5" />
        <rect x="90" y="15" width="5" height="15" rx="2.5" />
      </g>
      {/* red heart with white ECG pulse */}
      <path d="M60 50c-5-8-17-6-17 3 0 8 17 17 17 17s17-9 17-17c0-9-12-11-17-3z" fill="#EF4444" />
      <path
        d="M50 51h4l2.5-4 3 8 2.2-4H66"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* white bar chart (bottom) */}
      <rect x="24" y="82" width="13" height="20" rx="2.5" fill="#FFFFFF" />
      <rect x="42" y="74" width="13" height="28" rx="2.5" fill="#FFFFFF" />
      <rect x="60" y="78" width="13" height="24" rx="2.5" fill="#FFFFFF" />
      <rect x="78" y="71" width="13" height="31" rx="2.5" fill="#FFFFFF" />
      {/* green upward trend line over the bars */}
      <polyline
        points="26,78 45,68 63,72 81,60"
        fill="none"
        stroke="#22C55E"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="81" cy="60" r="3.5" fill="#22C55E" />
    </svg>
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
  meta?: ReportMeta | null;
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
  meta,
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
  const chronicConditions = reportData.chronic_conditions ?? [];

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
          <header className="bg-[#F5F0E6] px-6 py-6 sm:px-8">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[#FF5722]">
                  Family Health Manager
                </p>
                <p className="mt-1 text-[11px] text-gray-500">
                  Crafted with <span className="text-red-500">♥</span>
                </p>
                <h1 className="mt-3 text-2xl font-bold tracking-tight text-gray-900 sm:text-3xl">
                  Smart Health Report
                </h1>
                <p className="mt-1 text-sm text-gray-500">
                  Helping you understand your health better
                </p>
              </div>
              <div className="hidden shrink-0 sm:block">
                <SmartReportCoverGraphic />
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

            {chronicConditions.length > 0 && (
              <ReportSection eyebrow="Chronic conditions">
                <div className="space-y-2">
                  {chronicConditions.map((c, i) => (
                    <div
                      key={i}
                      className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 rounded-lg border border-gray-200 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <span className="text-[13px] font-semibold text-gray-900">{c.name}</span>
                        {c.since && (
                          <span className="ml-1.5 text-[11px] text-gray-500">since {c.since}</span>
                        )}
                        {c.note && (
                          <p className="mt-0.5 text-[12px] leading-relaxed text-gray-600">
                            {c.note}
                          </p>
                        )}
                      </div>
                      {c.status && (
                        <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-600">
                          {c.status}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </ReportSection>
            )}

            {systems.length > 0 && (
              <ReportSection eyebrow="Your body systems">
                <SystemStatusGrid systems={systems} />
              </ReportSection>
            )}

            {details.length > 0 && (
              <ReportSection eyebrow="Parameters in detail">
                <div className="space-y-3">
                  {details.map((d, i) => (
                    <ParameterTable
                      key={i}
                      detail={d}
                      warnings={verification?.warnings ?? undefined}
                    />
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

            <ReportFooter
              provider={provider}
              verification={verification}
              generatedAt={generatedAt}
              meta={meta}
            />
          </div>

          {/* Footer */}
          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 px-6 py-3 text-[11px] text-gray-500 sm:px-8">
            <span className="font-semibold uppercase tracking-wide">Family Health Manager</span>
            <span>
              {memberName} · {dateStr}
            </span>
          </footer>
        </article>
      </div>
    </div>
  );
}
