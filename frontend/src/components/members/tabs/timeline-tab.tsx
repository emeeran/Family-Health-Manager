import { memo, lazy, Suspense } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { HBA1C_CATEGORY_COLORS } from "@/lib/constants";
import { ChronicConditionCharts } from "@/components/members/chronic-condition-charts";
import type { MemberDetailResponse, Hba1cHistoryEntry } from "@/lib/types/member";

/* ── Lazy-loaded recharts ── */

const LazyHba1cChart = lazy(() =>
  import("recharts").then((mod) => ({
    default: ({
      data,
      minV,
      maxV,
      strokeColor,
    }: {
      data: { date: string; hba1c: number }[];
      minV: number;
      maxV: number;
      strokeColor: string;
    }) => (
      <mod.ResponsiveContainer width="100%" height={220}>
        <mod.LineChart data={data} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
          <defs>
            <linearGradient id="hba1cGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={strokeColor} stopOpacity={0.15} />
              <stop offset="95%" stopColor={strokeColor} stopOpacity={0} />
            </linearGradient>
          </defs>
          <mod.CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <mod.XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <mod.YAxis domain={[minV, maxV]} tick={{ fontSize: 11 }} />
          <mod.Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
          />
          <mod.ReferenceLine
            y={5.7}
            stroke="#f59e0b"
            strokeDasharray="5 5"
            label={{ value: "Prediabetes", fontSize: 10, fill: "#f59e0b" }}
          />
          <mod.ReferenceLine
            y={6.5}
            stroke="#ef4444"
            strokeDasharray="5 5"
            label={{ value: "Diabetes", fontSize: 10, fill: "#ef4444" }}
          />
          <mod.Area type="monotone" dataKey="hba1c" stroke="none" fill="url(#hba1cGrad)" />
          <mod.Line
            type="monotone"
            dataKey="hba1c"
            stroke={strokeColor}
            strokeWidth={2.5}
            dot={{ r: 4, fill: strokeColor, stroke: "#fff", strokeWidth: 2 }}
            activeDot={{ r: 6, fill: strokeColor, stroke: "#fff", strokeWidth: 2 }}
          />
        </mod.LineChart>
      </mod.ResponsiveContainer>
    ),
  }))
);

function ChartFallback() {
  return (
    <div className="flex items-center justify-center h-[180px] text-sm text-muted-foreground">
      Loading chart...
    </div>
  );
}

function getHba1cCategory(value: number): string {
  if (value < 5.7) return "Normal";
  if (value < 6.5) return "Prediabetes";
  return "Diabetes";
}

function TrendBadge({
  first,
  latest,
  lowerIsBetter = false,
}: {
  first: number;
  latest: number;
  lowerIsBetter?: boolean;
}) {
  const delta = latest - first;
  const absDelta = Math.abs(delta);
  if (absDelta < 0.1) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Minus className="h-3 w-3" />
        Stable
      </span>
    );
  }
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${improved ? "text-green-600" : "text-red-500"}`}
    >
      {delta > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {improved ? "Improving" : "Worsening"}
    </span>
  );
}

function ExpandedHba1cChart({ data }: { data: Hba1cHistoryEntry[] }) {
  const chartData = data.map((d) => ({ date: d.date.slice(0, 10), hba1c: d.hba1c_value }));
  const first = data[0].hba1c_value;
  const last = data[data.length - 1].hba1c_value;
  const category = getHba1cCategory(last);
  const vals = data.map((d) => d.hba1c_value);
  const minV = Math.floor(Math.min(...vals) * 10 - 5) / 10;
  const maxV = Math.ceil(Math.max(...vals) * 10 + 5) / 10;
  const strokeColor =
    category === "Normal" ? "#10b981" : category === "Prediabetes" ? "#f59e0b" : "#ef4444";

  if (data.length === 1) {
    return (
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-muted-foreground">HbA1c</p>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{last}%</span>
            <Badge
              variant="secondary"
              className={`text-[10px] px-1.5 py-0 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
            >
              {category}
            </Badge>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Add more readings to see trends over time.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-muted-foreground">HbA1c Trend</p>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {first}% → <span className="font-bold text-foreground">{last}%</span>
          </span>
          <Badge
            variant="secondary"
            className={`text-[10px] px-1.5 py-0 font-semibold ${HBA1C_CATEGORY_COLORS[category] ?? ""}`}
          >
            {category}
          </Badge>
          <TrendBadge first={first} latest={last} lowerIsBetter={true} />
        </div>
      </div>
      <Suspense fallback={<ChartFallback />}>
        <LazyHba1cChart data={chartData} minV={minV} maxV={maxV} strokeColor={strokeColor} />
      </Suspense>
    </div>
  );
}

interface TimelineTabProps {
  data: MemberDetailResponse;
}

export const TimelineTab = memo(function TimelineTab({ data }: TimelineTabProps) {
  const { hba1c_history, member } = data;

  return (
    <div className="space-y-3">
      {hba1c_history.length >= 1 ? (
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <ExpandedHba1cChart data={hba1c_history} />
          </CardContent>
        </Card>
      ) : (
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <p className="text-sm text-muted-foreground">
              No HbA1c data available. Add blood glucose or lab records to see trends.
            </p>
          </CardContent>
        </Card>
      )}

      <ChronicConditionCharts memberId={member.id} />
    </div>
  );
});
