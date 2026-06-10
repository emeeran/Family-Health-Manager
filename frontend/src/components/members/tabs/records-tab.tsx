import { memo, useMemo } from "react";
import { Link } from "react-router-dom";
import { FileText, BarChart3, CalendarDays } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { MemberDetailResponse } from "@/lib/types/member";

const TYPE_COLORS: Record<string, string> = {
  lab_report: "bg-blue-500",
  blood_glucose: "bg-violet-500",
  doctor_visit: "bg-emerald-500",
  hba1c: "bg-rose-500",
  prescription: "bg-amber-500",
  vaccination: "bg-teal-500",
  imaging: "bg-indigo-500",
  other: "bg-gray-400",
};

function ActivityCell({ count, label }: { count: number; label: string }) {
  const opacity = count === 0 ? 0.08 : count <= 1 ? 0.25 : count <= 3 ? 0.5 : count <= 5 ? 0.75 : 1;
  return (
    <div
      title={`${label}: ${count} records`}
      className="h-3.5 w-3.5 rounded-sm bg-primary cursor-default"
      style={{ opacity }}
    />
  );
}

interface RecordsTabProps {
  data: MemberDetailResponse;
}

export const RecordsTab = memo(function RecordsTab({ data }: RecordsTabProps) {
  const { recent_records } = data;

  const recordTypeDist = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of recent_records) {
      const type = r.record_type || "unknown";
      counts[type] = (counts[type] || 0) + 1;
    }
    return Object.entries(counts).sort(([, a], [, b]) => b - a);
  }, [recent_records]);

  const activityHeatmap = useMemo(() => {
    const now = new Date();
    const cells: { date: string; count: number; dayLabel: string }[] = [];
    for (let i = 83; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      const dayLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      const count = recent_records.filter(
        (r) =>
          r.record_date === dateStr || (r.record_date && r.record_date.slice(0, 10) === dateStr)
      ).length;
      cells.push({ date: dateStr, count, dayLabel });
    }
    return cells;
  }, [recent_records]);

  return (
    <div className="space-y-3">
      {/* Records by Type */}
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-blue-500" />
              Records by Type
            </div>
            <span className="text-[10px] text-muted-foreground">{recent_records.length} total</span>
          </div>
          {recordTypeDist.length > 0 ? (
            <div className="space-y-2">
              {recordTypeDist.map(([type, count]) => {
                const pct =
                  recent_records.length > 0 ? Math.round((count / recent_records.length) * 100) : 0;
                return (
                  <div key={type} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium">
                        {(RECORD_TYPE_LABELS as Record<string, string>)[type] || type}
                      </span>
                      <span className="text-muted-foreground tabular-nums">
                        {count} ({pct}%)
                      </span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${TYPE_COLORS[type] || "bg-gray-400"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex items-center gap-2 py-4 text-muted-foreground">
              <FileText className="h-4 w-4" />
              <span className="text-xs">No records yet</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Activity heatmap */}
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-violet-500" />
              Activity (12 weeks)
            </div>
            <span className="text-[10px] text-muted-foreground">
              {recent_records.length} records
            </span>
          </div>
          <div className="flex items-center gap-[3px] flex-wrap">
            {activityHeatmap.map((cell) => (
              <ActivityCell key={cell.date} count={cell.count} label={cell.dayLabel} />
            ))}
          </div>
          <div className="flex items-center justify-between mt-2 text-[10px] text-muted-foreground">
            <span>Less</span>
            <div className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-sm bg-primary/10" />
              <div className="h-2.5 w-2.5 rounded-sm bg-primary/25" />
              <div className="h-2.5 w-2.5 rounded-sm bg-primary/50" />
              <div className="h-2.5 w-2.5 rounded-sm bg-primary/75" />
              <div className="h-2.5 w-2.5 rounded-sm bg-primary" />
            </div>
            <span>More</span>
          </div>
        </CardContent>
      </Card>

      {/* Recent records list */}
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="text-sm font-semibold mb-3">Recent Records</div>
          {recent_records.length > 0 ? (
            <div className="space-y-1.5">
              {recent_records.slice(0, 15).map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold truncate">
                      {r.diagnosis ||
                        r.summary ||
                        (RECORD_TYPE_LABELS as Record<string, string>)[r.record_type] ||
                        r.record_type}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {r.provider_name || "No provider"}
                    </p>
                  </div>
                  <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                    {r.record_date}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 py-4 text-muted-foreground">
              <FileText className="h-4 w-4" />
              <span className="text-xs">No records yet</span>
            </div>
          )}
        </CardContent>
      </Card>

      <Link
        to="/records"
        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-teal-600 hover:bg-teal-50 transition-colors"
      >
        <FileText className="h-3.5 w-3.5" />
        View All Records
      </Link>
    </div>
  );
});
