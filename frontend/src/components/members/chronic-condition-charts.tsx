import { useState, useEffect, lazy, Suspense, memo } from "react";
// Recharts Tooltip formatter callback — typed to satisfy Formatter<ValueType, NameType>
type RechartsFormatter = (
  value: string | number | readonly (string | number)[] | undefined,
  name: string | number | undefined,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  item: any
) => [string, string];
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listRecords } from "@/lib/api/records";
import type { HealthRecordResponse } from "@/lib/types/health-record";

const LazyGlucoseChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({ data }: { data: { date: string; value: number; timing: string }[] }) => (
      <mod.ResponsiveContainer width="100%" height={200}>
        <mod.ScatterChart margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
          <mod.CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <mod.XAxis dataKey="date" tick={{ fontSize: 10 }} />
          <mod.YAxis
            domain={[40, 350]}
            tick={{ fontSize: 10 }}
            label={{ value: "mg/dL", angle: -90, position: "insideLeft", fontSize: 10 }}
          />
          <mod.Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e5e7eb" }}
            formatter={
              ((value: number, _name: string, props: { payload: { timing: string } }) => [
                `${value} mg/dL (${props.payload.timing === "before_food" ? "Fasting" : "Postprandial"})`,
                "Glucose",
              ]) as RechartsFormatter
            }
          />
          <mod.ReferenceLine y={100} stroke="#10b981" strokeDasharray="3 3" strokeOpacity={0.5} />
          <mod.ReferenceLine y={140} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.5} />
          <mod.ReferenceLine y={200} stroke="#ef4444" strokeDasharray="3 3" strokeOpacity={0.5} />
          <mod.Scatter data={data} fill="#f97316">
            {data.map((entry, index) => {
              const color =
                (entry.timing === "before_food" && entry.value < 100) ||
                (entry.timing === "after_food" && entry.value < 140)
                  ? "#10b981"
                  : entry.value < 200
                    ? "#f59e0b"
                    : "#ef4444";
              return (
                <mod.Dot
                  key={index}
                  cx={0}
                  cy={0}
                  r={4}
                  fill={color}
                  stroke="#fff"
                  strokeWidth={1.5}
                />
              );
            })}
          </mod.Scatter>
        </mod.ScatterChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

const LazyPDChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({
      data,
    }: {
      data: { date: string; time: string; severity: number; motor: string }[];
    }) => {
      const motorColors: Record<string, string> = {
        on: "#10b981",
        off: "#ef4444",
        wearing_off: "#f59e0b",
        dyskinesia: "#8b5cf6",
      };
      return (
        <mod.ResponsiveContainer width="100%" height={200}>
          <mod.ScatterChart margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
            <mod.CartesianGrid strokeDasharray="3 3" className="opacity-30" />
            <mod.XAxis
              dataKey="time"
              tick={{ fontSize: 10 }}
              label={{ value: "Time of day", position: "insideBottom", offset: -2, fontSize: 10 }}
            />
            <mod.YAxis
              domain={[0, 4]}
              ticks={[0, 1, 2, 3, 4]}
              tickFormatter={(v: number) => ["None", "Mild", "Mod", "Severe", ""][v] || ""}
              tick={{ fontSize: 9 }}
            />
            <mod.Tooltip
              contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e5e7eb" }}
              formatter={
                ((
                  value: number,
                  _name: string,
                  props: { payload: { motor: string; date: string } }
                ) => [
                  `Severity: ${["None", "Mild", "Moderate", "Severe"][value - 1] || "N/A"} (${props.payload.motor || "unknown"})`,
                  props.payload.date,
                ]) as RechartsFormatter
              }
            />
            <mod.Scatter data={data}>
              {data.map((entry, index) => (
                <mod.Dot
                  key={index}
                  cx={0}
                  cy={0}
                  r={5}
                  fill={motorColors[entry.motor] || "#94a3b8"}
                  stroke="#fff"
                  strokeWidth={1.5}
                />
              ))}
            </mod.Scatter>
          </mod.ScatterChart>
        </mod.ResponsiveContainer>
      );
    },
  }))
);

function ChartFallback() {
  return (
    <div className="flex items-center justify-center h-[180px] text-sm text-muted-foreground">
      Loading chart...
    </div>
  );
}

interface GlucosePoint {
  date: string;
  value: number;
  timing: string;
}

interface PDPoint {
  date: string;
  time: string;
  severity: number;
  motor: string;
}

function parseGlucoseRecords(records: HealthRecordResponse[]): GlucosePoint[] {
  const points: GlucosePoint[] = [];
  for (const r of records) {
    try {
      const parsed = JSON.parse(r.clinical_data);
      if (parsed._type === "structured" && parsed.glucose_value) {
        points.push({
          date: r.record_date.slice(0, 10),
          value: parseFloat(parsed.glucose_value),
          timing: parsed.meal_timing || "before_food",
        });
      }
    } catch {
      /* skip */
    }
  }
  return points;
}

function parsePDRecords(records: HealthRecordResponse[]): PDPoint[] {
  const severityMap: Record<string, number> = { none: 0, mild: 1, moderate: 2, severe: 3 };
  const points: PDPoint[] = [];
  for (const r of records) {
    try {
      const parsed = JSON.parse(r.clinical_data);
      if (parsed._type === "structured" && parsed._recordType === "parkinsons_log") {
        const maxSeverity = Math.max(
          severityMap[parsed.tremor_severity] || 0,
          severityMap[parsed.rigidity] || 0,
          severityMap[parsed.bradykinesia] || 0
        );
        if (maxSeverity > 0 || parsed.motor_state) {
          points.push({
            date: r.record_date.slice(0, 10),
            time: r.record_time || "12:00",
            severity: maxSeverity || 1,
            motor: parsed.motor_state || "on",
          });
        }
      }
    } catch {
      /* skip */
    }
  }
  return points;
}

export const ChronicConditionCharts = memo(function ChronicConditionCharts({
  memberId,
}: {
  memberId: string;
}) {
  const [glucoseData, setGlucoseData] = useState<GlucosePoint[]>([]);
  const [pdData, setPdData] = useState<PDPoint[]>([]);

  useEffect(() => {
    // Fetch recent records for glucose and PD types
    Promise.all([
      listRecords(memberId, { record_type: "blood_glucose" as never, limit: 50 }).catch(() => []),
      listRecords(memberId, { record_type: "parkinsons_log" as never, limit: 50 }).catch(() => []),
    ]).then(([glucoseRecords, pdRecords]) => {
      setGlucoseData(parseGlucoseRecords(glucoseRecords));
      setPdData(parsePDRecords(pdRecords));
    });
  }, [memberId]);

  if (glucoseData.length === 0 && pdData.length === 0) return null;

  return (
    <>
      {glucoseData.length >= 2 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">Glucose Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" /> Normal
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> Borderline
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-red-500" /> High
              </span>
            </div>
            <Suspense fallback={<ChartFallback />}>
              <LazyGlucoseChart data={glucoseData} />
            </Suspense>
          </CardContent>
        </Card>
      )}

      {pdData.length >= 2 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">PD Symptom Pattern</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" /> ON
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-red-500" /> OFF
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> Wearing Off
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-full bg-violet-500" /> Dyskinesia
              </span>
            </div>
            <Suspense fallback={<ChartFallback />}>
              <LazyPDChart data={pdData} />
            </Suspense>
          </CardContent>
        </Card>
      )}
    </>
  );
});
