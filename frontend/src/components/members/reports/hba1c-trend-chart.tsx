/**
 * HbA1c trend chart for the Health Assessment report.
 *
 * Plots the member's REAL serial HbA1c values (from `lab_results` via
 * `getHba1cHistory`) against the standard glycaemic bands
 * (normal <5.7%, pre-diabetes 5.7–6.4%, diabetes ≥6.5%). recharts is imported
 * lazily so it stays out of the main bundle. Renders nothing when there are
 * fewer than 2 data points.
 */

import { lazy, Suspense } from "react";
import { Activity } from "lucide-react";
import type { TooltipPayloadEntry, TooltipValueType } from "recharts";
import type { Hba1cHistoryEntry } from "@/lib/types/member";
import { cn } from "@/lib/utils";

// recharts' Tooltip formatter callback lacks precise types — mirror the cast
// used in chronic-condition-charts.tsx.
type RechartsFormatter = (
  value: TooltipValueType | undefined,
  name: string | number | undefined,
  item: TooltipPayloadEntry
) => [string, string];

const LazyHba1cChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({ data }: { data: { date: string; value: number }[] }) => (
      <mod.ResponsiveContainer width="100%" height={170}>
        <mod.AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id="hba1cFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#dc2626" stopOpacity={0.22} />
              <stop offset="95%" stopColor="#dc2626" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <mod.CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
          <mod.XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={{ stroke: "#e5e7eb" }}
          />
          <mod.YAxis
            domain={[4, "auto"]}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={false}
            width={34}
            unit="%"
          />
          <mod.Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid #e5e7eb",
            }}
            formatter={((value: number) => [`${value}%`, "HbA1c"]) as RechartsFormatter}
          />
          {/* Glycaemic bands: green normal, amber pre-diabetes, red diabetes */}
          <mod.ReferenceArea y1={4} y2={5.7} fill="#4ade80" fillOpacity={0.08} />
          <mod.ReferenceArea y1={5.7} y2={6.5} fill="#f59e0b" fillOpacity={0.1} />
          <mod.ReferenceArea y1={6.5} y2={20} fill="#ef4444" fillOpacity={0.08} />
          <mod.ReferenceLine y={6.5} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.45} />
          <mod.Area
            type="monotone"
            dataKey="value"
            stroke="#dc2626"
            strokeWidth={2}
            fill="url(#hba1cFill)"
            dot={{ r: 3, fill: "#dc2626", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </mod.AreaChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

function fmtShort(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

export function Hba1cTrendChart({ data }: { data: Hba1cHistoryEntry[] }) {
  const points = [...data]
    .filter((d) => typeof d.hba1c_value === "number" && !Number.isNaN(d.hba1c_value))
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => ({ date: fmtShort(d.date), value: d.hba1c_value }));
  if (points.length < 2) return null;

  const latest = points[points.length - 1];
  const first = points[0];
  const delta = latest.value - first.value;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Activity className="h-4 w-4 text-[#dc2626]" />
          <h3 className="text-[13px] font-bold text-gray-900">HbA1c trend</h3>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="font-bold tabular-nums text-gray-900">{latest.value}%</span>
          <span className="text-gray-400">latest</span>
          {delta !== 0 && (
            <span
              className={cn(
                "font-semibold tabular-nums",
                delta > 0 ? "text-red-600" : "text-emerald-600"
              )}
            >
              {delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} since {first.date}
            </span>
          )}
        </div>
      </div>
      <Suspense fallback={<div className="h-[170px]" />}>
        <LazyHba1cChart data={points} />
      </Suspense>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-gray-400">
        <span>
          <span className="text-emerald-500">■</span> Normal &lt;5.7
        </span>
        <span>
          <span className="text-amber-500">■</span> Pre-diabetes 5.7–6.4
        </span>
        <span>
          <span className="text-red-500">■</span> Diabetes ≥6.5
        </span>
      </div>
    </div>
  );
}
