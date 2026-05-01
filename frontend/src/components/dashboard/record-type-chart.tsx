"use client";

import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface RecordTypeChartProps {
  records: HealthRecordResponse[];
}

const COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
];

const TYPE_COLORS: Record<string, string> = {
  doctor_visit: "hsl(220 70% 55%)",
  lab_report: "hsl(160 60% 45%)",
  rx_eyeglass: "hsl(270 65% 60%)",
  blood_glucose: "hsl(38 80% 55%)",
  misc_record: "hsl(215 15% 50%)",
};

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, unknown> }>;
}) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload as Record<string, unknown>;
  const name = String(data.name ?? "");
  const value = Number(data.value ?? 0);
  const total = Number(data.total ?? 0);
  const pct = total > 0 ? ((value / total) * 100).toFixed(1) : "0";
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{name}</p>
      <p className="text-muted-foreground">
        {value} records ({pct}%)
      </p>
    </div>
  );
}

function renderLegend(value: string, entry: { color?: string }) {
  return (
    <span className="text-xs" style={{ color: entry.color }}>
      {value}
    </span>
  );
}

export function RecordTypeChart({ records }: RecordTypeChartProps) {
  const data = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of records) {
      counts[r.record_type] = (counts[r.record_type] || 0) + 1;
    }
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    return Object.entries(counts)
      .map(([type, count]) => ({
        name: RECORD_TYPE_LABELS[type as keyof typeof RECORD_TYPE_LABELS] || type,
        value: count,
        type,
        total,
      }))
      .sort((a, b) => b.value - a.value);
  }, [records]);

  if (data.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Record Types</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="w-full overflow-x-auto">
          <ResponsiveContainer width="100%" height={220} minWidth={280}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={45}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {data.map((entry, i) => (
                  <Cell key={i} fill={TYPE_COLORS[entry.type] || COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
              <Legend formatter={renderLegend} wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
