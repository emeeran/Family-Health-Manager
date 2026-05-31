import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { useMemo, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface HealthTrendsChartProps {
  records: HealthRecordResponse[];
  memberNames: Record<string, string>;
}

/** Extract numeric value from clinical_data for charting.
 *  Handles both structured JSON and plain text. */
function extractNumeric(clinicalData: string): number | null {
  if (!clinicalData) return null;
  // Try structured JSON first
  try {
    const parsed = JSON.parse(clinicalData);
    if (parsed._type === "structured") {
      // Blood glucose: use glucose_value
      if (parsed.glucose_value !== undefined) return parseFloat(parsed.glucose_value);
      // HbA1c value
      if (parsed.hba1c_value !== undefined) return parseFloat(parsed.hba1c_value);
      // Lab report: try first test result
      if (Array.isArray(parsed.tests) && parsed.tests.length > 0) {
        const firstResult = parsed.tests[0].result;
        if (firstResult) {
          const num = parseFloat(firstResult);
          if (!isNaN(num)) return num;
        }
      }
    }
  } catch {
    // Not JSON, try text extraction
  }
  const match = clinicalData.match(/(\d+\.?\d*)\s*(mg\/d[lL]|%|mmol\/l|mmHg|bpm|kg)/i);
  return match ? parseFloat(match[1]) : null;
}

interface ChartRow {
  date: string;
  [memberName: string]: string | number;
}

const COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
];

export const HealthTrendsChart = memo(function HealthTrendsChart({
  records,
  memberNames,
}: HealthTrendsChartProps) {
  const { chartData, members } = useMemo(() => {
    const dataByDate: Record<string, ChartRow> = {};

    for (const record of records) {
      const value = extractNumeric(record.clinical_data);
      if (value === null) continue;

      const dateKey = record.record_date;
      const memberName = memberNames[record.family_member_id] || "Unknown";

      if (!dataByDate[dateKey]) dataByDate[dateKey] = { date: dateKey };
      dataByDate[dateKey][memberName] = value;
    }

    const chartData = Object.values(dataByDate)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .slice(-20);

    const members = [...new Set(records.map((r) => memberNames[r.family_member_id] || "Unknown"))];
    return { chartData, members };
  }, [records, memberNames]);

  if (chartData.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Health Trends</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="w-full overflow-x-auto">
          <ResponsiveContainer width="100%" height={220} minWidth={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                className="text-muted-foreground"
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis tick={{ fontSize: 11 }} className="text-muted-foreground" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "var(--radius)",
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {members.map((name, i) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
});
