import { Shield, Clock, CalendarPlus } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PreventiveItem } from "@/lib/types/dashboard";

interface PreventiveTimelineProps {
  items: PreventiveItem[];
  onSetReminder: (memberId: string, title: string) => void;
}

const dueStatusConfig = {
  overdue: {
    dotClass: "bg-red-500",
    label: "Overdue",
    badgeClass: "bg-red-100 text-red-800 border border-red-200",
    bg: "bg-red-50 border-red-200",
  },
  due_soon: {
    dotClass: "bg-amber-500",
    label: "Due Soon",
    badgeClass: "bg-amber-100 text-amber-800 border border-amber-200",
    bg: "bg-amber-50 border-amber-200",
  },
  upcoming: {
    dotClass: "bg-emerald-500",
    label: "Upcoming",
    badgeClass: "bg-emerald-100 text-emerald-800 border border-emerald-200",
    bg: "bg-emerald-50 border-emerald-200",
  },
} as const;

const priorityConfig = {
  high: "bg-red-100 text-red-700 border border-red-200",
  medium: "bg-amber-100 text-amber-700 border border-amber-200",
  low: "bg-blue-100 text-blue-700 border border-blue-200",
} as const;

export function PreventiveTimeline({ items, onSetReminder }: PreventiveTimelineProps) {
  const sorted = [...items].sort((a, b) => {
    const order = { overdue: 0, due_soon: 1, upcoming: 2 };
    return order[a.due_status] - order[b.due_status];
  });

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="text-base font-semibold flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10">
            <Shield className="h-4 w-4 text-emerald-600" />
          </div>
          Preventive Care
          {items.length > 0 && (
            <Badge className="text-[11px] font-bold px-2 py-0.5 bg-emerald-100 text-emerald-800 border border-emerald-200">
              {items.length}
            </Badge>
          )}
        </div>
      </div>
      <CardContent>
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
            <Shield className="h-8 w-8 text-emerald-400" />
            <p className="text-sm font-medium">All preventive care up to date</p>
          </div>
        ) : (
          <div className="relative pl-6">
            {/* Timeline line */}
            <div className="absolute left-[6px] top-2 bottom-2 w-px bg-border" />

            <div className="space-y-3">
              {sorted.map((item, idx) => {
                const statusConfig = dueStatusConfig[item.due_status];
                return (
                  <div key={`${item.member_id}-${item.category}-${idx}`} className="relative">
                    {/* Timeline dot */}
                    <div
                      className={`absolute -left-6 top-1.5 h-3 w-3 rounded-full border-2 border-background ${statusConfig.dotClass}`}
                    />

                    <div
                      className={`flex items-start justify-between gap-2 rounded-xl border px-3 py-2.5 ${statusConfig.bg}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-semibold truncate">{item.recommendation}</p>
                          <Badge
                            className={`text-[11px] font-bold shrink-0 px-1.5 py-0.5 ${priorityConfig[item.priority]}`}
                          >
                            {item.priority}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-sm text-muted-foreground font-medium">
                            {item.member_name}
                          </span>
                          <Badge
                            className={`text-[11px] font-bold px-1.5 py-0.5 ${statusConfig.badgeClass}`}
                          >
                            <Clock className="h-2.5 w-2.5 mr-0.5" />
                            {statusConfig.label}
                          </Badge>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetReminder(item.member_id, item.recommendation)}
                        className="shrink-0 p-1 h-auto text-muted-foreground hover:text-foreground"
                      >
                        <CalendarPlus className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
