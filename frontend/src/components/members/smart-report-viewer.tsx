import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { InsightReport, parseSections } from "@/components/members/insight-report-viewer";
import type { VerificationResult } from "@/lib/types/message";
import {
  ArrowLeft,
  Download,
  Activity,
  AlertTriangle,
  CheckCircle2,
  Minus,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Info,
  Stethoscope,
} from "lucide-react";

/* ── JSON types ── */

interface SystemGlance {
  system: string;
  status: "needs_attention" | "ideal" | "no_data";
  summary: string;
  parameters_total: number;
  parameters_out_of_range: number;
  parameters_improved: number;
}

interface LabParameter {
  name: string;
  value: string;
  unit: string;
  date: string;
  status: "in_range" | "out_of_range" | "borderline" | "critical";
  reference_range: string;
  trend: "improved" | "further_decreased" | "stable" | "new_abnormal" | "not_available";
  previous_values: { date: string; value: string }[];
}

interface OrganDetail {
  system: string;
  parameters: LabParameter[];
}

interface ParameterInFocus {
  name: string;
  system: string;
  explanation: string;
  significance: string;
  trend_note: string;
  recommendation: string;
}

interface SmartRecommendation {
  category: string;
  priority: "high" | "medium" | "low";
  action: string;
  reasoning: string;
}

interface SmartReportData {
  systems_at_a_glance: SystemGlance[];
  organ_details: OrganDetail[];
  parameters_in_focus: ParameterInFocus[];
  recommendations: SmartRecommendation[];
}

/* ── Helpers ── */

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  needs_attention: { bg: "bg-red-100", text: "text-red-700", label: "Needs Attention" },
  ideal: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Ideal" },
  no_data: { bg: "bg-gray-100", text: "text-gray-500", label: "No Data" },
};

const PARAM_STATUS: Record<string, { bg: string; text: string }> = {
  in_range: { bg: "bg-emerald-100", text: "text-emerald-700" },
  out_of_range: { bg: "bg-red-100", text: "text-red-700" },
  borderline: { bg: "bg-amber-100", text: "text-amber-700" },
  critical: { bg: "bg-red-200", text: "text-red-800" },
};

const TREND_ICON: Record<string, { icon: typeof TrendingUp; color: string }> = {
  improved: { icon: TrendingUp, color: "text-emerald-600" },
  further_decreased: { icon: TrendingDown, color: "text-red-600" },
  stable: { icon: Minus, color: "text-gray-500" },
  new_abnormal: { icon: AlertTriangle, color: "text-amber-600" },
  not_available: { icon: Minus, color: "text-gray-400" },
};

const PRIORITY_STYLE: Record<string, { bg: string; text: string }> = {
  high: { bg: "bg-red-100", text: "text-red-700" },
  medium: { bg: "bg-amber-100", text: "text-amber-700" },
  low: { bg: "bg-blue-100", text: "text-blue-700" },
};

function tryParseSmartReport(response: string): SmartReportData | null {
  try {
    const cleaned = response
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/\s*```\s*$/i, "")
      .trim();
    const parsed = JSON.parse(cleaned);
    if (parsed.systems_at_a_glance && parsed.organ_details) {
      return parsed as SmartReportData;
    }
  } catch {
    // Not valid JSON — fall back to prose
  }
  return null;
}

/* ── Sub-components ── */

function SystemCard({ system }: { system: SystemGlance }) {
  const badge = STATUS_BADGE[system.status] || STATUS_BADGE.no_data;
  const borderClass =
    system.status === "needs_attention"
      ? "border-red-200 bg-red-50/30"
      : system.status === "ideal"
        ? "border-emerald-200 bg-emerald-50/30"
        : "border-gray-200 bg-gray-50/30";

  return (
    <Card className={`shadow-none ${borderClass}`}>
      <CardContent className="p-3.5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">{system.system}</h3>
          <Badge className={`text-[10px] px-1.5 py-0 ${badge.bg} ${badge.text} border-0`}>
            {badge.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mb-2">{system.summary}</p>
        <div className="flex gap-3 text-[11px]">
          <span className="text-muted-foreground">
            Total: <strong className="text-foreground">{system.parameters_total}</strong>
          </span>
          {system.parameters_out_of_range > 0 && (
            <span className="text-red-600">
              Out of range: <strong>{system.parameters_out_of_range}</strong>
            </span>
          )}
          {system.parameters_improved > 0 && (
            <span className="text-emerald-600">
              Improved: <strong>{system.parameters_improved}</strong>
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ParameterTable({ detail }: { detail: OrganDetail }) {
  if (!detail.parameters || detail.parameters.length === 0) return null;
  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
        <Activity className="h-4 w-4 text-purple-600" />
        {detail.system}
      </h3>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/50 text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="py-2 px-3 text-left font-medium">Parameter</th>
              <th className="py-2 px-3 text-left font-medium">Value</th>
              <th className="py-2 px-3 text-left font-medium hidden sm:table-cell">Ref Range</th>
              <th className="py-2 px-3 text-left font-medium hidden md:table-cell">Date</th>
              <th className="py-2 px-3 text-left font-medium">Status</th>
              <th className="py-2 px-3 text-left font-medium">Trend</th>
            </tr>
          </thead>
          <tbody>
            {detail.parameters.map((param, i) => {
              const statusStyle = PARAM_STATUS[param.status] || PARAM_STATUS.in_range;
              const trendInfo = TREND_ICON[param.trend] || TREND_ICON.not_available;
              const TrendIcon = trendInfo.icon;
              return (
                <tr key={i} className="border-t hover:bg-muted/20 transition-colors">
                  <td className="py-2 px-3 font-medium text-xs">{param.name}</td>
                  <td className="py-2 px-3 text-xs">
                    {param.value} <span className="text-muted-foreground">{param.unit}</span>
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden sm:table-cell">
                    {param.reference_range}
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden md:table-cell">
                    {param.date}
                  </td>
                  <td className="py-2 px-3">
                    <Badge
                      className={`text-[10px] px-1.5 py-0 ${statusStyle.bg} ${statusStyle.text} border-0 capitalize`}
                    >
                      {param.status.replace(/_/g, " ")}
                    </Badge>
                  </td>
                  <td className="py-2 px-3">
                    <span className="inline-flex items-center gap-1">
                      <TrendIcon className={`h-3 w-3 ${trendInfo.color}`} />
                      <span className={`text-[11px] ${trendInfo.color}`}>
                        {param.trend === "not_available" ? "--" : param.trend.replace(/_/g, " ")}
                      </span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FocusCard({ param }: { param: ParameterInFocus }) {
  return (
    <Card className="shadow-none border-l-4 border-l-amber-400">
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
          <h4 className="text-sm font-semibold">{param.name}</h4>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {param.system}
          </Badge>
        </div>
        <div className="space-y-2.5 text-xs">
          {param.explanation && (
            <div>
              <span className="font-semibold text-muted-foreground flex items-center gap-1 mb-0.5">
                <Info className="h-3 w-3" /> What is this?
              </span>
              <p className="text-foreground/80 leading-relaxed">{param.explanation}</p>
            </div>
          )}
          {param.significance && (
            <div>
              <span className="font-semibold text-muted-foreground flex items-center gap-1 mb-0.5">
                <AlertTriangle className="h-3 w-3" /> Why it matters
              </span>
              <p className="text-foreground/80 leading-relaxed">{param.significance}</p>
            </div>
          )}
          {param.trend_note && (
            <div>
              <span className="font-semibold text-muted-foreground flex items-center gap-1 mb-0.5">
                <TrendingDown className="h-3 w-3" /> Trend
              </span>
              <p className="text-foreground/80 leading-relaxed">{param.trend_note}</p>
            </div>
          )}
          {param.recommendation && (
            <div>
              <span className="font-semibold text-muted-foreground flex items-center gap-1 mb-0.5">
                <Stethoscope className="h-3 w-3" /> Recommendation
              </span>
              <p className="text-foreground/80 leading-relaxed">{param.recommendation}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationCard({ rec }: { rec: SmartRecommendation }) {
  const style = PRIORITY_STYLE[rec.priority] || PRIORITY_STYLE.low;
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/20 hover:bg-muted/30 transition-colors">
      <Badge
        className={`text-[10px] px-1.5 py-0 shrink-0 ${style.bg} ${style.text} border-0 capitalize`}
      >
        {rec.priority}
      </Badge>
      <div className="min-w-0">
        <p className="text-xs font-semibold">{rec.action}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">{rec.reasoning}</p>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 mt-1">
          {rec.category}
        </Badge>
      </div>
    </div>
  );
}

/* ── Main viewer ── */

interface SmartReportViewerProps {
  response: string;
  provider: string;
  generatedAt: string;
  verification: VerificationResult | null;
  memberName: string;
  onBack: () => void;
}

export function SmartReportViewer({
  response,
  provider,
  generatedAt,
  verification,
  memberName,
  onBack,
}: SmartReportViewerProps) {
  const reportData = useMemo(() => tryParseSmartReport(response), [response]);

  function handleExportPDF() {
    if (!reportData) return;
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const dateStr = new Date(generatedAt).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });

    const s = "border:1px solid #DDD;padding:6px 8px;font-size:10px;";
    const sh = s + "background:#F5F5F5;font-weight:bold;font-size:9px;text-align:left;";

    // Systems grid
    const systemsHtml = reportData.systems_at_a_glance
      .map(
        (sys) => `
      <div style="display:inline-block;vertical-align:top;width:48%;margin:1%;padding:10px;border-radius:6px;
        border:1px solid ${sys.status === "needs_attention" ? "#FCA5A5" : sys.status === "ideal" ? "#86EFAC" : "#E5E7EB"};
        background:${sys.status === "needs_attention" ? "#FEF2F2" : sys.status === "ideal" ? "#F0FDF4" : "#F9FAFB"}">
        <div style="font-weight:bold;font-size:11px;margin-bottom:4px">${esc(sys.system)}</div>
        <div style="font-size:9px;color:#6b7280">${esc(sys.summary)}</div>
      </div>`
      )
      .join("");

    // Parameter tables
    const tablesHtml = reportData.organ_details
      .filter((d) => d.parameters && d.parameters.length > 0)
      .map(
        (detail) => `
      <h3 style="font-size:11px;color:#7C3AED;margin:14px 0 6px;font-weight:bold">${esc(detail.system)}</h3>
      <table style="width:100%;border-collapse:collapse"><thead><tr>
        <th style="${sh}">Parameter</th><th style="${sh}">Value</th><th style="${sh}">Ref Range</th>
        <th style="${sh}">Date</th><th style="${sh}">Status</th><th style="${sh}">Trend</th>
      </tr></thead><tbody>
      ${detail.parameters
        .map(
          (p) => `<tr>
        <td style="${s}font-weight:600">${esc(p.name)}</td>
        <td style="${s}">${esc(p.value)} ${esc(p.unit)}</td>
        <td style="${s};color:#6b7280">${esc(p.reference_range)}</td>
        <td style="${s};color:#6b7280">${esc(p.date)}</td>
        <td style="${s}">${esc(p.status.replace(/_/g, " "))}</td>
        <td style="${s}">${esc(p.trend === "not_available" ? "--" : p.trend.replace(/_/g, " "))}</td>
      </tr>`
        )
        .join("")}
      </tbody></table>`
      )
      .join("");

    // Parameters in focus
    const focusHtml = reportData.parameters_in_focus
      .map(
        (p) => `
      <div style="margin-bottom:12px;padding:10px;border-left:4px solid #F59E0B;background:#FFFBEB;border-radius:4px">
        <div style="font-weight:bold;font-size:11px;margin-bottom:6px">${esc(p.name)} <span style="font-weight:normal;font-size:9px;color:#6b7280">— ${esc(p.system)}</span></div>
        ${p.explanation ? `<div style="font-size:10px;margin-bottom:4px"><strong>What:</strong> ${esc(p.explanation)}</div>` : ""}
        ${p.significance ? `<div style="font-size:10px;margin-bottom:4px"><strong>Significance:</strong> ${esc(p.significance)}</div>` : ""}
        ${p.trend_note ? `<div style="font-size:10px;margin-bottom:4px"><strong>Trend:</strong> ${esc(p.trend_note)}</div>` : ""}
        ${p.recommendation ? `<div style="font-size:10px"><strong>Action:</strong> ${esc(p.recommendation)}</div>` : ""}
      </div>`
      )
      .join("");

    // Recommendations
    const recsHtml = reportData.recommendations
      .map(
        (r) => `
      <div style="margin-bottom:8px;padding:8px;border-radius:4px;background:#F5F5F5">
        <span style="display:inline-block;font-size:9px;font-weight:bold;padding:1px 6px;border-radius:3px;margin-right:6px;
          background:${r.priority === "high" ? "#FEE2E2" : r.priority === "medium" ? "#FEF3C7" : "#DBEAFE"};
          color:${r.priority === "high" ? "#B91C1C" : r.priority === "medium" ? "#92400E" : "#1E40AF"}">
          ${esc(r.priority.toUpperCase())}
        </span>
        <span style="font-size:10px;font-weight:600">${esc(r.action)}</span>
        <div style="font-size:9px;color:#6b7280;margin-top:2px">${esc(r.reasoning)}</div>
      </div>`
      )
      .join("");

    const html = `<!DOCTYPE html><html><head><title>Smart Report — ${esc(memberName)}</title>
<style>
  @page { margin: 0.75in 1in; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; font-size: 11px; line-height: 1.6; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #7C3AED; border-bottom: 2px solid #E5E7EB; padding-bottom: 4px; margin: 18px 0 10px; }
</style></head>
<body>
<div style="text-align:center;margin-bottom:16px;border-bottom:3px solid #7C3AED;padding-bottom:12px">
  <div style="font-size:16px;font-weight:bold;color:#1f2937">${esc(memberName)} — Smart Report</div>
  <div style="font-size:10px;color:#6b7280;margin-top:4px">${dateStr} &middot; via ${esc(provider)}</div>
  <div style="font-size:9px;color:#9ca3af;margin-top:2px">Exported ${now}</div>
</div>

<h2>Body Systems at a Glance</h2>
<div style="margin-bottom:12px">${systemsHtml}</div>

<h2>Parameter Details</h2>
${tablesHtml}

${reportData.parameters_in_focus.length > 0 ? `<h2>Parameters in Focus</h2>${focusHtml}` : ""}

${reportData.recommendations.length > 0 ? `<h2>Clinical Recommendations</h2>${recsHtml}` : ""}

<div style="margin-top:20px;padding-top:8px;border-top:1px solid #d1d5db;font-size:9px;color:#9ca3af">
  AI-generated for informational purposes only. Review with your healthcare provider. Family Health Manager.
</div>
</body></html>`;

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 200);
  }

  // Fallback to prose InsightReport if JSON parsing fails
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

  const attentionSystems = reportData.systems_at_a_glance.filter(
    (s) => s.status === "needs_attention"
  );
  const idealSystems = reportData.systems_at_a_glance.filter((s) => s.status === "ideal");
  const outOfRangeParams = reportData.parameters_in_focus.length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} className="h-8 px-2">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Activity className="h-5 w-5 text-purple-600" />
              Smart Report
            </h2>
            <p className="text-xs text-muted-foreground">
              {memberName} &middot;{" "}
              {new Date(generatedAt).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}{" "}
              via <span className="font-semibold">{provider}</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <VerificationBadge verification={verification} />
          <Button variant="outline" size="sm" onClick={handleExportPDF} className="gap-1 h-8">
            <Download className="h-3.5 w-3.5" />
            PDF
          </Button>
        </div>
      </div>

      {/* Summary banner */}
      <div className="flex items-center gap-4 p-3 rounded-lg bg-muted/30 border">
        {attentionSystems.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span className="font-semibold text-red-700">{attentionSystems.length}</span>
            <span className="text-muted-foreground">systems need attention</span>
          </div>
        )}
        {idealSystems.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            <span className="font-semibold text-emerald-700">{idealSystems.length}</span>
            <span className="text-muted-foreground">systems ideal</span>
          </div>
        )}
        {outOfRangeParams > 0 && (
          <div className="flex items-center gap-1.5 text-xs">
            <TrendingDown className="h-4 w-4 text-amber-500" />
            <span className="font-semibold text-amber-700">{outOfRangeParams}</span>
            <span className="text-muted-foreground">parameters in focus</span>
          </div>
        )}
      </div>

      {/* Systems at a Glance */}
      <div>
        <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
          <Activity className="h-4 w-4 text-purple-600" />
          Body Systems at a Glance
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {reportData.systems_at_a_glance.map((sys) => (
            <SystemCard key={sys.system} system={sys} />
          ))}
        </div>
      </div>

      {/* Per-Organ Parameter Tables */}
      {reportData.organ_details.filter((d) => d.parameters && d.parameters.length > 0).length >
        0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
            <ArrowRight className="h-4 w-4 text-purple-600" />
            Parameter Details by System
          </h3>
          {reportData.organ_details.map((detail) => (
            <ParameterTable key={detail.system} detail={detail} />
          ))}
        </div>
      )}

      {/* Parameters in Focus */}
      {reportData.parameters_in_focus.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Parameters in Focus
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            {reportData.parameters_in_focus.map((param, i) => (
              <FocusCard key={i} param={param} />
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {reportData.recommendations.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
            <Stethoscope className="h-4 w-4 text-purple-600" />
            Clinical Recommendations
          </h3>
          <div className="space-y-2">
            {reportData.recommendations.map((rec, i) => (
              <RecommendationCard key={i} rec={rec} />
            ))}
          </div>
        </div>
      )}

      {/* Disclaimer footer */}
      <div className="text-center text-[11px] text-muted-foreground pt-3 border-t">
        AI-generated for informational purposes only. Review with your healthcare provider.
      </div>
    </div>
  );
}
