import { useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { InsightReport } from "@/components/members/insight-report-viewer";
import type { VerificationResult } from "@/lib/types/message";
import {
  ArrowLeft,
  Download,
  Heart,
  AlertTriangle,
  CheckCircle2,
  Minus,
  TrendingUp,
  TrendingDown,
  Info,
  Stethoscope,
  Shield,
  Activity,
  Eye,
  Droplets,
  Brain,
  Bone,
  FlaskConical,
  Zap,
  Sparkles,
  FileHeart,
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

/* ── Visual config ── */

const SYSTEM_ICONS: Record<string, typeof Heart> = {
  "Blood Health": Droplets,
  "Heart Health": Heart,
  "GI & Liver": FlaskConical,
  "Kidney Health": Droplets,
  "Blood Glucose": Zap,
  "Hormone Health": Brain,
  "Bone & Muscle": Bone,
  "Skin & Hair": Eye,
  "Immune System": Shield,
};

const SYSTEM_GRADIENTS: Record<string, string> = {
  needs_attention: "from-red-500/10 via-red-500/5 to-transparent",
  ideal: "from-emerald-500/10 via-emerald-500/5 to-transparent",
  no_data: "from-gray-400/5 via-gray-400/3 to-transparent",
};

const SYSTEM_ACCENT: Record<string, string> = {
  needs_attention: "bg-red-500",
  ideal: "bg-emerald-500",
  no_data: "bg-gray-300",
};

const STATUS_DOT: Record<string, string> = {
  needs_attention: "bg-red-500 shadow-red-500/30",
  ideal: "bg-emerald-500 shadow-emerald-500/30",
  no_data: "bg-gray-300",
};

const PARAM_ROW_BG: Record<string, string> = {
  in_range: "",
  out_of_range: "bg-red-50/60",
  borderline: "bg-amber-50/60",
  critical: "bg-red-100/70",
};

const PARAM_PILL: Record<string, { bg: string; text: string; ring: string }> = {
  in_range: { bg: "bg-emerald-50", text: "text-emerald-700", ring: "ring-emerald-200" },
  out_of_range: { bg: "bg-red-50", text: "text-red-700", ring: "ring-red-200" },
  borderline: { bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-200" },
  critical: { bg: "bg-red-100", text: "text-red-800", ring: "ring-red-300" },
};

const TREND_VISUAL: Record<string, { icon: typeof TrendingUp; fg: string; bg: string }> = {
  improved: { icon: TrendingUp, fg: "text-emerald-600", bg: "bg-emerald-50" },
  further_decreased: { icon: TrendingDown, fg: "text-red-600", bg: "bg-red-50" },
  stable: { icon: Minus, fg: "text-gray-500", bg: "bg-gray-50" },
  new_abnormal: { icon: AlertTriangle, fg: "text-amber-600", bg: "bg-amber-50" },
  not_available: { icon: Minus, fg: "text-gray-400", bg: "bg-gray-50" },
};

const PRIORITY_GRADIENT: Record<
  string,
  { bar: string; bg: string; text: string; icon: typeof AlertTriangle }
> = {
  high: {
    bar: "bg-gradient-to-r from-red-500 to-red-600",
    bg: "bg-red-50 border-red-200",
    text: "text-red-800",
    icon: AlertTriangle,
  },
  medium: {
    bar: "bg-gradient-to-r from-amber-400 to-amber-500",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-800",
    icon: Info,
  },
  low: {
    bar: "bg-gradient-to-r from-blue-400 to-blue-500",
    bg: "bg-blue-50 border-blue-200",
    text: "text-blue-800",
    icon: CheckCircle2,
  },
};

/* ── Parser ── */

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

/* ── SVG ring gauge ── */

function StatusRing({
  value,
  max,
  size = 44,
  stroke = 3.5,
  color,
}: {
  value: number;
  max: number;
  size?: number;
  stroke?: number;
  color: string;
}) {
  const r = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;
  const pct = max > 0 ? value / max : 0;
  const offset = circ - pct * circ;
  const cx = size / 2;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="shrink-0">
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-gray-100"
        />
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cx})`}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[11px] font-bold" style={{ color }}>
          {value}
        </span>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function SystemCard({ system }: { system: SystemGlance }) {
  const Icon = SYSTEM_ICONS[system.system] || Activity;
  const gradient = SYSTEM_GRADIENTS[system.status];
  const accent = SYSTEM_ACCENT[system.status];
  const dot = STATUS_DOT[system.status];
  const ringColor =
    system.status === "needs_attention"
      ? "#EF4444"
      : system.status === "ideal"
        ? "#22C55E"
        : "#D1D5DB";
  const outPct =
    system.parameters_total > 0 ? system.parameters_out_of_range / system.parameters_total : 0;

  return (
    <div
      className={`relative overflow-hidden rounded-xl border bg-gradient-to-br ${gradient} transition-shadow hover:shadow-md`}
    >
      <div className={`absolute top-0 left-0 w-full h-1 ${accent}`} />
      <div className="p-3 pt-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <div
              className={`flex items-center justify-center w-8 h-8 rounded-lg ${system.status === "needs_attention" ? "bg-red-100 text-red-600" : system.status === "ideal" ? "bg-emerald-100 text-emerald-600" : "bg-gray-100 text-gray-400"}`}
            >
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <h4 className="text-[12px] font-semibold leading-tight">{system.system}</h4>
              <div className="flex items-center gap-1 mt-0.5">
                <span className={`inline-block h-1.5 w-1.5 rounded-full shadow-sm ${dot}`} />
                <span className="text-[10px] text-muted-foreground">
                  {system.status === "needs_attention"
                    ? "Needs Attention"
                    : system.status === "ideal"
                      ? "All Clear"
                      : "No Data"}
                </span>
              </div>
            </div>
          </div>
          <StatusRing
            value={system.parameters_out_of_range}
            max={system.parameters_total}
            size={36}
            stroke={3}
            color={ringColor}
          />
        </div>
        <p className="text-[10px] text-muted-foreground mb-2 leading-relaxed">{system.summary}</p>
        {system.parameters_total > 0 && (
          <div className="flex items-center gap-1.5">
            <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${outPct > 0.5 ? "bg-gradient-to-r from-red-400 to-red-500" : outPct > 0 ? "bg-gradient-to-r from-amber-400 to-amber-500" : "bg-emerald-400"}`}
                style={{ width: `${outPct * 100}%` }}
              />
            </div>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {system.parameters_out_of_range}/{system.parameters_total}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function ParameterTable({ detail }: { detail: OrganDetail }) {
  if (!detail.parameters || detail.parameters.length === 0) return null;

  const outOfRange = detail.parameters.filter((p) => p.status !== "in_range").length;

  return (
    <div className="rounded-xl border overflow-hidden bg-white">
      {/* Table header strip */}
      <div
        className={`flex items-center gap-2.5 px-4 py-2.5 border-b ${outOfRange > 0 ? "bg-red-50/60 border-red-100" : "bg-emerald-50/60 border-emerald-100"}`}
      >
        <div
          className={`flex items-center justify-center w-7 h-7 rounded-lg shrink-0 ${outOfRange > 0 ? "bg-red-100 text-red-600" : "bg-emerald-100 text-emerald-600"}`}
        >
          {(() => {
            const Ic = SYSTEM_ICONS[detail.system] || Activity;
            return <Ic className="h-3.5 w-3.5" />;
          })()}
        </div>
        <span className="text-xs font-bold flex-1">{detail.system}</span>
        <span className="text-[11px] text-muted-foreground">
          {outOfRange} of {detail.parameters.length} out of range
        </span>
        {outOfRange > 0 && (
          <Badge className="text-[10px] px-1.5 py-0 bg-red-100 text-red-700 border-0">
            {outOfRange} flagged
          </Badge>
        )}
      </div>
      <table className="w-full">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-muted-foreground/70 border-b bg-muted/20">
            <th className="py-2 px-3 text-left font-medium">Parameter</th>
            <th className="py-2 px-3 text-left font-medium">Value</th>
            <th className="py-2 px-3 text-left font-medium hidden sm:table-cell">Reference</th>
            <th className="py-2 px-3 text-left font-medium hidden md:table-cell">Date</th>
            <th className="py-2 px-3 text-center font-medium">Status</th>
            <th className="py-2 px-3 text-left font-medium">Trend</th>
          </tr>
        </thead>
        <tbody>
          {detail.parameters.map((param, i) => {
            const pill = PARAM_PILL[param.status] || PARAM_PILL.in_range;
            const trend = TREND_VISUAL[param.trend] || TREND_VISUAL.not_available;
            const TrendIcon = trend.icon;
            const rowBg = PARAM_ROW_BG[param.status] || "";
            return (
              <tr
                key={i}
                className={`border-b last:border-b-0 transition-colors ${rowBg} hover:bg-muted/10`}
              >
                <td className="py-2.5 px-3">
                  <span
                    className={`text-xs font-medium ${param.status === "critical" ? "text-red-800" : param.status === "out_of_range" ? "text-red-700" : ""}`}
                  >
                    {param.name}
                  </span>
                </td>
                <td className="py-2.5 px-3">
                  <span className="text-xs font-bold tabular-nums">{param.value}</span>
                  <span className="text-[10px] text-muted-foreground ml-0.5">{param.unit}</span>
                </td>
                <td className="py-2.5 px-3 text-[11px] text-muted-foreground hidden sm:table-cell tabular-nums">
                  {param.reference_range}
                </td>
                <td className="py-2.5 px-3 text-[11px] text-muted-foreground hidden md:table-cell">
                  {param.date}
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${pill.bg} ${pill.text} ${pill.ring} capitalize`}
                  >
                    {param.status.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="py-2.5 px-3">
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 ${trend.bg}`}
                  >
                    <TrendIcon className={`h-3 w-3 ${trend.fg}`} />
                    <span className={`text-[10px] font-medium ${trend.fg}`}>
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
  );
}

function FocusCard({ param }: { param: ParameterInFocus }) {
  return (
    <div className="group relative rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50/80 via-white to-orange-50/40 overflow-hidden transition-shadow hover:shadow-md">
      {/* Top accent bar */}
      <div className="h-1 bg-gradient-to-r from-amber-400 via-orange-400 to-red-400" />
      <div className="p-4">
        <div className="flex items-start gap-3 mb-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-amber-100 to-orange-100 text-amber-700 shrink-0">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-bold text-gray-900">{param.name}</h4>
            <Badge
              variant="outline"
              className="text-[10px] px-1.5 py-0 mt-0.5 border-amber-200 text-amber-700"
            >
              {param.system}
            </Badge>
          </div>
        </div>
        <div className="space-y-2.5 ml-12">
          {param.explanation && (
            <FocusDetailRow
              icon={<Info className="h-3 w-3" />}
              label="What is this?"
              text={param.explanation}
            />
          )}
          {param.significance && (
            <FocusDetailRow
              icon={<AlertTriangle className="h-3 w-3" />}
              label="Why it matters"
              text={param.significance}
              color="text-amber-700"
            />
          )}
          {param.trend_note && (
            <FocusDetailRow
              icon={<TrendingDown className="h-3 w-3" />}
              label="Trend"
              text={param.trend_note}
              color="text-red-600"
            />
          )}
          {param.recommendation && (
            <FocusDetailRow
              icon={<Stethoscope className="h-3 w-3" />}
              label="Recommendation"
              text={param.recommendation}
              color="text-purple-700"
            />
          )}
        </div>
      </div>
    </div>
  );
}

function FocusDetailRow({
  icon,
  label,
  text,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
  color?: string;
}) {
  return (
    <div>
      <div
        className={`flex items-center gap-1 mb-0.5 text-[11px] font-semibold ${color || "text-muted-foreground"}`}
      >
        {icon}
        <span className="ml-0.5">{label}</span>
      </div>
      <p className="text-[12px] text-gray-700 leading-relaxed">{text}</p>
    </div>
  );
}

function RecommendationCard({ rec, index }: { rec: SmartRecommendation; index: number }) {
  const style = PRIORITY_GRADIENT[rec.priority] || PRIORITY_GRADIENT.low;
  const PriorityIcon = style.icon;
  return (
    <div
      className={`relative rounded-xl border overflow-hidden transition-shadow hover:shadow-md ${style.bg}`}
    >
      <div className={`absolute top-0 left-0 w-1 h-full ${style.bar}`} />
      <div className="flex items-start gap-3 p-3.5 pl-5">
        <div
          className={`flex items-center justify-center w-8 h-8 rounded-lg shrink-0 ${style.bg} ${style.text}`}
        >
          <PriorityIcon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={`text-[10px] font-bold uppercase tracking-wider ${style.text}`}>
              {rec.priority}
            </span>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-current/20">
              {rec.category}
            </Badge>
          </div>
          <p className="text-[13px] font-semibold text-gray-900 leading-snug">{rec.action}</p>
          <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{rec.reasoning}</p>
        </div>
        <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0">
          #{index + 1}
        </span>
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

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onBack();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  /* ── PDF Export ── */
  function handleExportPDF() {
    if (!reportData) return;
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const time = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    const genDate = new Date(generatedAt);
    const dateStr = genDate.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const reportId = `SR-${genDate.getFullYear()}${String(genDate.getMonth() + 1).padStart(2, "0")}${String(genDate.getDate()).padStart(2, "0")}-${String(genDate.getHours()).padStart(2, "0")}${String(genDate.getMinutes()).padStart(2, "0")}`;

    const tc = "border:1px solid #E5E7EB;padding:7px 10px;font-size:10px;";
    const thc =
      tc +
      "background:#F9FAFB;font-weight:bold;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;color:#6B7280;text-align:left;";

    // Systems grid
    const systemsHtml = reportData.systems_at_a_glance
      .map((sys) => {
        const accentBar =
          sys.status === "needs_attention"
            ? "#EF4444"
            : sys.status === "ideal"
              ? "#22C55E"
              : "#D1D5DB";
        const dotColor = accentBar;
        const bgColor =
          sys.status === "needs_attention"
            ? "#FEF2F2"
            : sys.status === "ideal"
              ? "#F0FDF4"
              : "#FAFAFA";
        const outPct =
          sys.parameters_total > 0 ? (sys.parameters_out_of_range / sys.parameters_total) * 100 : 0;
        const barColor =
          outPct > 50
            ? "linear-gradient(to right,#F87171,#EF4444)"
            : outPct > 0
              ? "linear-gradient(to right,#FBBF24,#F59E0B)"
              : "#34D399";
        return `
        <div style="display:inline-block;vertical-align:top;width:48%;margin:0.8% 0.8%;border-radius:10px;border:1px solid #E5E7EB;background:${bgColor};overflow:hidden">
          <div style="height:4px;background:${accentBar}"></div>
          <div style="padding:12px 14px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <div style="font-weight:bold;font-size:11px;color:#111827">${esc(sys.system)}</div>
              <div style="display:flex;align-items:center;gap:4px">
                <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${dotColor}"></span>
                <span style="font-size:9px;color:#6B7280">${sys.status === "needs_attention" ? "Needs Attention" : sys.status === "ideal" ? "All Clear" : "No Data"}</span>
              </div>
            </div>
            <div style="font-size:9px;color:#6B7280;margin-bottom:8px;line-height:1.4">${esc(sys.summary)}</div>
            ${
              sys.parameters_total > 0
                ? `
            <div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;height:5px;border-radius:3px;background:#F3F4F6;overflow:hidden">
                <div style="height:100%;border-radius:3px;background:${barColor};width:${outPct}%"></div>
              </div>
              <span style="font-size:9px;color:#9CA3AF;font-variant-numeric:tabular-nums">${sys.parameters_out_of_range}/${sys.parameters_total}</span>
            </div>
            `
                : ""
            }
          </div>
        </div>`;
      })
      .join("");

    // Parameter tables
    const tablesHtml = reportData.organ_details
      .filter((d) => d.parameters && d.parameters.length > 0)
      .map((detail) => {
        const outCount = detail.parameters.filter((p) => p.status !== "in_range").length;
        const hdrBg = outCount > 0 ? "#FEF2F2" : "#F0FDF4";
        const hdrBorder = outCount > 0 ? "#FECACA" : "#BBF7D0";
        return `
        <div style="margin-bottom:18px;border-radius:10px;border:1px solid #E5E7EB;overflow:hidden">
          <div style="background:${hdrBg};padding:8px 12px;border-bottom:1px solid ${hdrBorder};display:flex;align-items:center;gap:8px">
            <span style="font-weight:bold;font-size:11px;color:#111827">${esc(detail.system)}</span>
            <span style="font-size:9px;color:#6B7280">${outCount} of ${detail.parameters.length} out of range</span>
            ${outCount > 0 ? `<span style="display:inline-block;font-size:8px;font-weight:bold;padding:1px 6px;border-radius:4px;background:#FEE2E2;color:#B91C1C">${outCount} flagged</span>` : ""}
          </div>
          <table style="width:100%;border-collapse:collapse"><thead><tr>
            <th style="${thc}">Parameter</th><th style="${thc}">Value</th><th style="${thc}">Reference</th>
            <th style="${thc}">Date</th><th style="${thc}text-align:center">Status</th><th style="${thc}">Trend</th>
          </tr></thead><tbody>
          ${detail.parameters
            .map((p) => {
              const rowBg =
                p.status === "out_of_range"
                  ? "background:#FEF2F2;"
                  : p.status === "critical"
                    ? "background:#FEE2E2;"
                    : p.status === "borderline"
                      ? "background:#FFFBEB;"
                      : "";
              const statusColor =
                p.status === "in_range"
                  ? "#059669"
                  : p.status === "out_of_range"
                    ? "#DC2626"
                    : p.status === "critical"
                      ? "#991B1B"
                      : "#D97706";
              const statusBg =
                p.status === "in_range"
                  ? "#ECFDF5"
                  : p.status === "out_of_range"
                    ? "#FEF2F2"
                    : p.status === "critical"
                      ? "#FEE2E2"
                      : "#FFFBEB";
              return `<tr style="${rowBg}">
              <td style="${tc}font-weight:600;color:#111827">${esc(p.name)}</td>
              <td style="${tc}"><span style="font-weight:bold">${esc(p.value)}</span> <span style="color:#9CA3AF">${esc(p.unit)}</span></td>
              <td style="${tc};color:#6B7280;font-variant-numeric:tabular-nums">${esc(p.reference_range)}</td>
              <td style="${tc};color:#6B7280">${esc(p.date)}</td>
              <td style="${tc}text-align:center"><span style="display:inline-block;padding:1px 8px;border-radius:99px;font-size:9px;font-weight:600;color:${statusColor};background:${statusBg}">${esc(p.status.replace(/_/g, " "))}</span></td>
              <td style="${tc};color:#6B7280">${esc(p.trend === "not_available" ? "--" : p.trend.replace(/_/g, " "))}</td>
            </tr>`;
            })
            .join("")}
          </tbody></table>
        </div>`;
      })
      .join("");

    // Parameters in focus
    const focusHtml = reportData.parameters_in_focus
      .map(
        (p) => `
      <div style="margin-bottom:14px;border-radius:10px;border:1px solid #FDE68A;overflow:hidden">
        <div style="height:4px;background:linear-gradient(to right,#FBBF24,#F97316,#EF4444)"></div>
        <div style="padding:12px 14px;background:linear-gradient(135deg,#FFFBEB 0%,#FFF7ED 50%,#FFF1F2 100%)">
          <div style="font-weight:bold;font-size:12px;color:#92400E;margin-bottom:8px">${esc(p.name)} <span style="font-weight:normal;font-size:10px;color:#92400E80">&mdash; ${esc(p.system)}</span></div>
          ${p.explanation ? `<div style="font-size:10px;margin-bottom:5px;color:#374151"><strong style="color:#6B7280">What:</strong> ${esc(p.explanation)}</div>` : ""}
          ${p.significance ? `<div style="font-size:10px;margin-bottom:5px;color:#374151"><strong style="color:#B45309">Why it matters:</strong> ${esc(p.significance)}</div>` : ""}
          ${p.trend_note ? `<div style="font-size:10px;margin-bottom:5px;color:#374151"><strong style="color:#DC2626">Trend:</strong> ${esc(p.trend_note)}</div>` : ""}
          ${p.recommendation ? `<div style="font-size:10px;color:#374151"><strong style="color:#7C3AED">Action:</strong> ${esc(p.recommendation)}</div>` : ""}
        </div>
      </div>`
      )
      .join("");

    // Recommendations
    const recsHtml = reportData.recommendations
      .map((r) => {
        const barColor =
          r.priority === "high"
            ? "linear-gradient(to right,#EF4444,#DC2626)"
            : r.priority === "medium"
              ? "linear-gradient(to right,#FBBF24,#F59E0B)"
              : "linear-gradient(to right,#60A5FA,#3B82F6)";
        const bgColor =
          r.priority === "high" ? "#FEF2F2" : r.priority === "medium" ? "#FFFBEB" : "#EFF6FF";
        const borderColor =
          r.priority === "high" ? "#FECACA" : r.priority === "medium" ? "#FDE68A" : "#BFDBFE";
        const textColor =
          r.priority === "high" ? "#991B1B" : r.priority === "medium" ? "#92400E" : "#1E40AF";
        return `
        <div style="margin-bottom:10px;border-radius:8px;border:1px solid ${borderColor};overflow:hidden;background:${bgColor};position:relative">
          <div style="position:absolute;top:0;left:0;width:4px;height:100%;background:${barColor};border-radius:8px 0 0 8px"></div>
          <div style="padding:10px 14px 10px 18px">
            <div style="margin-bottom:3px">
              <span style="display:inline-block;font-size:8px;font-weight:bold;text-transform:uppercase;letter-spacing:0.1em;color:${textColor};background:${bgColor};padding:1px 6px;border-radius:3px;border:1px solid ${borderColor}">${esc(r.priority)}</span>
              <span style="font-size:9px;color:#6B7280;margin-left:6px">${esc(r.category)}</span>
            </div>
            <div style="font-size:11px;font-weight:600;color:#111827;line-height:1.4">${esc(r.action)}</div>
            <div style="font-size:9px;color:#6B7280;margin-top:3px;line-height:1.4">${esc(r.reasoning)}</div>
          </div>
        </div>`;
      })
      .join("");

    const attentionCount = reportData.systems_at_a_glance.filter(
      (s) => s.status === "needs_attention"
    ).length;
    const idealCount = reportData.systems_at_a_glance.filter((s) => s.status === "ideal").length;

    const html = `<!DOCTYPE html><html><head><title>Smart Report — ${esc(memberName)}</title>
<style>
  @page { margin: 0.6in 0.75in; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1f2937; font-size: 11px; line-height: 1.6; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  h2 { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: #7C3AED; margin: 22px 0 10px; display: flex; align-items: center; gap: 6px; }
  h2::before { content: ''; display: inline-block; width: 3px; height: 14px; background: linear-gradient(to bottom, #7C3AED, #A855F7); border-radius: 2px; }
</style></head>
<body>

<!-- Cover Header -->
<div style="border-radius:12px;overflow:hidden;margin-bottom:20px;border:1px solid #E5E7EB">
  <div style="background:linear-gradient(135deg,#7C3AED 0%,#A855F7 40%,#C084FC 100%);padding:24px 28px 20px">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
      <div style="width:24px;height:24px;border-radius:6px;background:rgba(255,255,255,0.2);display:flex;align-items:center;justify-content:center">
        <span style="font-size:12px;color:white">&#x2695;</span>
      </div>
      <span style="font-size:10px;font-weight:600;letter-spacing:0.2em;color:rgba(255,255,255,0.8)">DAWNSTAR FAMILY HEALTH KEEPER</span>
    </div>
    <h1 style="font-size:22px;font-weight:bold;color:white;margin-bottom:6px">Smart Health Report</h1>
    <div style="display:flex;align-items:center;gap:8px">
      <span style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.95)">${esc(memberName)}</span>
      <span style="color:rgba(255,255,255,0.4)">&middot;</span>
      <span style="font-size:11px;color:rgba(255,255,255,0.7)">${dateStr}</span>
    </div>
  </div>
  <div style="background:white;padding:12px 28px;display:flex;justify-content:space-between;align-items:center">
    <div style="display:flex;gap:20px">
      <div style="display:flex;align-items:center;gap:4px">
        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#EF4444"></span>
        <span style="font-size:10px;color:#374151"><strong>${attentionCount}</strong> systems need attention</span>
      </div>
      <div style="display:flex;align-items:center;gap:4px">
        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22C55E"></span>
        <span style="font-size:10px;color:#374151"><strong>${idealCount}</strong> systems all clear</span>
      </div>
    </div>
    <div style="text-align:right;font-size:9px;color:#9CA3AF">
      <div>Report ID: <span style="font-family:monospace">${reportId}</span></div>
      <div>AI Model: ${esc(provider)} &middot; Exported ${now}, ${time}</div>
    </div>
  </div>
</div>

<h2>Body Systems at a Glance</h2>
<div style="margin-bottom:8px">${systemsHtml}</div>

<h2>Parameter Details by System</h2>
${tablesHtml}

${reportData.parameters_in_focus.length > 0 ? `<h2>Parameters in Focus</h2>${focusHtml}` : ""}

${reportData.recommendations.length > 0 ? `<h2>Clinical Recommendations</h2>${recsHtml}` : ""}

<!-- Footer -->
<div style="margin-top:24px;padding:12px 0;border-top:2px solid #111827;display:flex;justify-content:space-between;align-items:flex-end">
  <div>
    <p style="font-size:11px;font-weight:600;color:#374151;margin-bottom:3px">Disclaimer</p>
    <p style="font-size:9px;color:#9CA3AF;line-height:1.5;max-width:70%">This report is AI-generated for informational purposes only. It does not constitute medical advice, diagnosis, or treatment recommendations. Always review with a qualified healthcare professional.</p>
  </div>
  <div style="text-align:right;font-size:9px;color:#D1D5DB">
    <div style="font-weight:600;color:#9CA3AF">DAWNSTAR Family Health Keeper</div>
    <div>${esc(provider)} &middot; ${dateStr}</div>
  </div>
</div>
</body></html>`;

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 200);
  }

  /* ── Fallback ── */
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

  /* ── Computed values ── */
  const attentionSystems = reportData.systems_at_a_glance.filter(
    (s) => s.status === "needs_attention"
  );
  const idealSystems = reportData.systems_at_a_glance.filter((s) => s.status === "ideal");
  const focusParams = reportData.parameters_in_focus.length;
  const genDate = new Date(generatedAt);
  const reportId = `SR-${genDate.getFullYear()}${String(genDate.getMonth() + 1).padStart(2, "0")}${String(genDate.getDate()).padStart(2, "0")}-${String(genDate.getHours()).padStart(2, "0")}${String(genDate.getMinutes()).padStart(2, "0")}`;
  const dateStr = genDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const detailsWithData = reportData.organ_details.filter(
    (d) => d.parameters && d.parameters.length > 0
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sticky toolbar */}
      <div className="sticky top-0 z-20 border-b border-gray-200 bg-white/95 backdrop-blur-sm print:hidden">
        <div className="max-w-[960px] mx-auto flex items-center justify-between px-6 h-11">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </button>
          <div className="flex items-center gap-3">
            <VerificationBadge verification={verification} />
            <Button size="sm" variant="outline" onClick={handleExportPDF} className="gap-1.5">
              <Download className="h-3.5 w-3.5" />
              Export PDF
            </Button>
            <span className="text-[11px] font-mono text-gray-400">{reportId}</span>
          </div>
        </div>
      </div>

      <div className="max-w-[960px] mx-auto px-6 py-6">
        {/* Hero header */}
        <div className="rounded-2xl overflow-hidden border border-purple-200/50 shadow-lg mb-6">
          <div className="bg-gradient-to-br from-purple-700 via-purple-600 to-indigo-600 px-6 py-5">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-white/15">
                <FileHeart className="h-4 w-4 text-white" />
              </div>
              <span className="text-[10px] font-semibold uppercase tracking-[0.25em] text-white/60">
                Dawnstar Family Health Keeper
              </span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Smart Health Report</h1>
            <div className="flex items-center gap-2 mt-1.5 text-sm">
              <span className="font-semibold text-white/95">{memberName}</span>
              <span className="text-white/30">&middot;</span>
              <span className="text-white/60">{dateStr}</span>
            </div>
          </div>
          <div className="bg-white px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-5">
              {attentionSystems.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full bg-red-500 shadow-sm shadow-red-500/30" />
                  <span className="text-xs text-gray-600">
                    <strong className="text-red-700">{attentionSystems.length}</strong> need
                    attention
                  </span>
                </div>
              )}
              {idealSystems.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/30" />
                  <span className="text-xs text-gray-600">
                    <strong className="text-emerald-700">{idealSystems.length}</strong> all clear
                  </span>
                </div>
              )}
              {focusParams > 0 && (
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-xs text-gray-600">
                    <strong className="text-amber-700">{focusParams}</strong> in focus
                  </span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-[10px] font-medium text-purple-700 ring-1 ring-inset ring-purple-200">
                <Sparkles className="h-3 w-3" /> AI-Generated
              </span>
              <span className="font-mono">{reportId}</span>
            </div>
          </div>
        </div>

        {/* Body Systems at a Glance */}
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="h-5 w-1 rounded-full bg-gradient-to-b from-purple-600 to-indigo-500" />
            <h2 className="text-sm font-bold text-gray-900">Body Systems at a Glance</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {reportData.systems_at_a_glance.map((sys) => (
              <SystemCard key={sys.system} system={sys} />
            ))}
          </div>
        </section>

        {/* Parameter Details by System */}
        {detailsWithData.length > 0 && (
          <section className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-5 w-1 rounded-full bg-gradient-to-b from-blue-600 to-cyan-500" />
              <h2 className="text-sm font-bold text-gray-900">Parameter Details</h2>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {detailsWithData.length} systems
              </Badge>
            </div>
            <div className="space-y-4">
              {reportData.organ_details.map((detail) => (
                <ParameterTable key={detail.system} detail={detail} />
              ))}
            </div>
          </section>
        )}

        {/* Parameters in Focus */}
        {reportData.parameters_in_focus.length > 0 && (
          <section className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-5 w-1 rounded-full bg-gradient-to-b from-amber-500 to-red-500" />
              <h2 className="text-sm font-bold text-gray-900">Parameters in Focus</h2>
              <Badge className="text-[10px] px-1.5 py-0 bg-amber-100 text-amber-700 border-0">
                {reportData.parameters_in_focus.length} flagged
              </Badge>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {reportData.parameters_in_focus.map((param, i) => (
                <FocusCard key={i} param={param} />
              ))}
            </div>
          </section>
        )}

        {/* Clinical Recommendations */}
        {reportData.recommendations.length > 0 && (
          <section className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <div className="h-5 w-1 rounded-full bg-gradient-to-b from-emerald-600 to-teal-500" />
              <h2 className="text-sm font-bold text-gray-900">Clinical Recommendations</h2>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {reportData.recommendations.length}
              </Badge>
            </div>
            <div className="space-y-2.5">
              {reportData.recommendations
                .sort((a, b) =>
                  a.priority === "high"
                    ? -1
                    : b.priority === "high"
                      ? 1
                      : a.priority === "medium"
                        ? -1
                        : 1
                )
                .map((rec, i) => (
                  <RecommendationCard key={i} rec={rec} index={i} />
                ))}
            </div>
          </section>
        )}

        {/* Footer */}
        <div className="pt-4 border-t-2 border-gray-900">
          <p className="text-[12px] text-gray-500 mb-2">
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
      </div>
    </div>
  );
}
