import { memo, useMemo } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { formatRelativeTime } from "@/lib/utils";
import { useRecordQuickView } from "@/components/records/record-quick-view-provider";
import { EmptyState } from "@/components/shared/empty-state";
import { CalendarClock, FileText, Activity } from "lucide-react";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface DashboardReminder {
  id: string;
  title: string;
  start_datetime: string | null;
  reminder_type: string;
  family_member_id: string | null;
}

interface ActivityFeedProps {
  records: HealthRecordResponse[];
  memberNames: Record<string, string>;
  upcomingReminders: DashboardReminder[];
}

function extractPreview(
  clinicalData: string | null | undefined,
  diagnosis: string | null | undefined
): string {
  if (diagnosis) return diagnosis;
  if (!clinicalData) return "";
  try {
    const parsed = JSON.parse(clinicalData);
    if (parsed.chief_complaint) return parsed.chief_complaint;
    if (parsed.glucose_value) return `Glucose: ${parsed.glucose_value} mg/dL`;
    if (parsed.hba1c_value) return `HbA1c: ${parsed.hba1c_value}%`;
    if (Array.isArray(parsed.lab_results) && parsed.lab_results.length > 0)
      return `${parsed.lab_results.length} tests`;
  } catch {
    const first = clinicalData.split("\n")[0];
    return first.length > 60 ? first.slice(0, 60) + "..." : first;
  }
  return "";
}

const RECORD_BORDER_COLORS: Record<string, string> = {
  lab_record: "border-l-blue-500",
  consultation: "border-l-emerald-500",
  prescription: "border-l-violet-500",
  vitals: "border-l-amber-500",
  reminder: "border-l-orange-500",
};

function getRecordBorderColor(type: string, recordType?: string): string {
  if (type === "reminder") return "border-l-orange-500";
  return (recordType && RECORD_BORDER_COLORS[recordType]) || "border-l-muted-foreground/20";
}

export const ActivityFeed = memo(function ActivityFeed({
  records,
  memberNames,
  upcomingReminders,
}: ActivityFeedProps) {
  const { openQuickView } = useRecordQuickView();

  // Combine records and reminders into a single feed sorted by date
  const feedItems = useMemo(() => {
    const items: {
      id: string;
      type: "record" | "reminder";
      recordType?: string;
      title: string;
      subtitle: string;
      badge?: string;
      date: string;
      onClick?: () => void;
      overdue?: boolean;
    }[] = [];

    for (const r of records.slice(0, 8)) {
      const preview = extractPreview(r.clinical_data, r.diagnosis);
      items.push({
        id: r.id,
        type: "record",
        recordType: r.record_type,
        title: memberNames[r.family_member_id] || "Unknown",
        subtitle: preview,
        badge: (RECORD_TYPE_LABELS as Record<string, string>)[r.record_type] || r.record_type,
        date: r.record_date,
        onClick: () => openQuickView(r.id, r.family_member_id),
      });
    }

    for (const rem of upcomingReminders.slice(0, 3)) {
      const isOverdue = rem.start_datetime ? new Date(rem.start_datetime) < new Date() : false;
      items.push({
        id: rem.id,
        type: "reminder",
        title: rem.title,
        subtitle: rem.start_datetime ? formatRelativeTime(rem.start_datetime) : "No date",
        date: rem.start_datetime || "",
        overdue: isOverdue,
      });
    }

    return items;
  }, [records, upcomingReminders, memberNames, openQuickView]);

  if (feedItems.length === 0) {
    return (
      <div className="space-y-2">
        <p className="section-label">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--brand-accent)] mr-2 align-middle" />
          Activity
        </p>
        <EmptyState
          variant="compact"
          icon={<Activity className="h-8 w-8 text-muted-foreground/40" />}
          title="No recent activity"
          description="Health records and reminders will appear here as you add them."
          action={
            <Link to="/people">
              <Button size="sm" variant="outline">
                Add your first record
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="section-label">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--brand-accent)] mr-2 align-middle" />
          Activity
        </p>
        <Link to="/records" className="text-xs text-primary hover:underline underline-offset-2">
          View all
        </Link>
      </div>
      <div className="space-y-0.5">
        {feedItems.map((item) => (
          <button
            key={item.id}
            onClick={item.onClick}
            className={`feed-item flex items-center gap-3 w-full text-left rounded-lg px-3 py-2 border-l-[3px] rounded-l-none hover:bg-muted/30 transition-colors ${getRecordBorderColor(item.type, item.recordType)}`}
          >
            <div className="shrink-0">
              {item.type === "record" ? (
                <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center">
                  <FileText className="h-3.5 w-3.5 text-primary" />
                </div>
              ) : (
                <div
                  className={`h-7 w-7 rounded-full flex items-center justify-center ${
                    item.overdue ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted"
                  }`}
                >
                  <CalendarClock
                    className={`h-3.5 w-3.5 ${item.overdue ? "text-amber-600" : "text-muted-foreground"}`}
                  />
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium truncate">{item.title}</p>
                {item.badge && (
                  <Badge variant="outline" className="text-[10px] shrink-0 px-1.5 py-0">
                    {item.badge}
                  </Badge>
                )}
                {item.overdue && (
                  <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded border border-red-200 shrink-0">
                    OVERDUE
                  </span>
                )}
              </div>
              {item.subtitle && (
                <p className="text-xs text-muted-foreground truncate">{item.subtitle}</p>
              )}
            </div>
            <span className="text-[10px] text-muted-foreground shrink-0">
              {item.date ? formatRelativeTime(item.date) : ""}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
});
