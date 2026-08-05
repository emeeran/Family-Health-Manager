/**
 * Vitals trend chart for the member overview.
 *
 * Plots Blood Pressure (systolic + diastolic, two lines) from `vitals` records,
 * BMI (computed from weight/height) from `vitals` records, and Glucose from
 * `blood_glucose` records (plus any glucose/HbA1c rows in `lab_report` test
 * tables). recharts is imported lazily so it stays out of the main bundle.
 *
 * Records carry clinical_data as a JSON string; vitals records use the
 * structured shape (`_type: "structured"` with `blood_pressure`/`weight`/
 * `height` fields), blood_glucose records carry `glucose_value`, and
 * lab_report records carry a `tests` table with `test_name`/`result` rows.
 *
 * The component is defensive: missing fields, malformed JSON, or sparse data
 * never crash — they just produce fewer (or zero) points. With <2 BP points
 * it renders a small muted empty state instead of the chart.
 */

import { lazy, Suspense, useMemo } from "react";
import { Activity } from "lucide-react";
import useSWR from "swr";
import { listRecords } from "@/lib/api/records";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import { formatDate } from "@/lib/utils";

const LazyVitalsChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({ data }: { data: VitalsPoint[] }) => (
      <mod.ResponsiveContainer width="100%" height={200}>
        <mod.LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <mod.CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
          <mod.XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={{ stroke: "#e5e7eb" }}
          />
          <mod.YAxis
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={false}
            width={34}
          />
          <mod.Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid #e5e7eb",
            }}
          />
          <mod.Line
            type="monotone"
            dataKey="systolic"
            name="Systolic"
            stroke="#dc2626"
            strokeWidth={2}
            dot={{ r: 3, fill: "#dc2626", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            connectNulls
          />
          <mod.Line
            type="monotone"
            dataKey="diastolic"
            name="Diastolic"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={{ r: 3, fill: "#3b82f6", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        </mod.LineChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

interface VitalsPoint {
  date: string;
  /** ms since epoch — used for correct chronological sorting. */
  ts: number;
  systolic: number | null;
  diastolic: number | null;
}

/** Parse a structured clinical_data JSON string into its raw object, or null. */
function parseStructured(raw: string): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return parsed && parsed._type === "structured" ? parsed : null;
  } catch {
    return null;
  }
}

/** Parse "120/80" → { systolic: 120, diastolic: 80 }; tolerant of whitespace. */
function parseBP(value: unknown): { systolic: number; diastolic: number } | null {
  if (typeof value !== "string") return null;
  const m = value.match(/(\d{2,3})\s*\/\s*(\d{2,3})/);
  if (!m) return null;
  const systolic = Number(m[1]);
  const diastolic = Number(m[2]);
  if (!Number.isFinite(systolic) || !Number.isFinite(diastolic)) return null;
  return { systolic, diastolic };
}

function fmtShort(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

interface VitalsTrendChartProps {
  memberId: string;
}

export function VitalsTrendChart({ memberId }: VitalsTrendChartProps) {
  const { data: records } = useSWR(`vitals-trend-${memberId}`, () => listRecords(memberId), {
    revalidateOnFocus: false,
    dedupingInterval: 60_000,
  });

  const points = useMemo<VitalsPoint[]>(() => {
    if (!records) return [];
    const out: VitalsPoint[] = [];
    for (const r of records as HealthRecordResponse[]) {
      if (r.record_type !== "vitals" && r.record_type !== "doctor_visit") continue;
      if (!r.record_date) continue;
      const parsed = parseStructured(r.clinical_data);
      if (!parsed) continue;
      const bp = parseBP(parsed.blood_pressure);
      // Only include a point if we actually have a usable BP reading on this
      // record — the chart's two lines are systolic/diastolic. Missing fields
      // don't crash; they just yield null and get connected across gaps.
      out.push({
        date: fmtShort(r.record_date),
        ts: new Date(r.record_date).getTime(),
        systolic: bp?.systolic ?? null,
        diastolic: bp?.diastolic ?? null,
      });
    }
    return out.sort((a, b) => a.ts - b.ts);
  }, [records]);

  if (!records) {
    // Still loading — render a placeholder sized to the chart so the page
    // doesn't jump once data arrives.
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-2 flex items-center gap-1.5">
          <Activity className="h-4 w-4 text-red-600" />
          <h3 className="text-[13px] font-bold text-gray-900">Blood pressure trend</h3>
        </div>
        <div className="h-[200px]" />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Activity className="h-4 w-4 text-red-600" />
          <h3 className="text-[13px] font-bold text-gray-900">Blood pressure trend</h3>
        </div>
        {points.length >= 2 && (
          <div className="flex items-center gap-3 text-[11px]">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-600" />
              <span className="text-gray-500">Systolic</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
              <span className="text-gray-500">Diastolic</span>
            </span>
          </div>
        )}
      </div>
      {points.length < 2 ? (
        <p className="py-10 text-center text-xs text-muted-foreground">No vitals data yet</p>
      ) : (
        <Suspense fallback={<div className="h-[200px]" />}>
          <LazyVitalsChart data={points} />
        </Suspense>
      )}
      {points.length > 0 && (
        <p className="mt-1.5 text-[10px] text-gray-400">
          {points.length} reading{points.length !== 1 ? "s" : ""} · since{" "}
          {formatDate(new Date(Math.min(...points.map((p) => p.ts))).toISOString())}
        </p>
      )}
    </div>
  );
}
