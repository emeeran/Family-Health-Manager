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
    <Card className="shadow-none">
      <CardContent className="pt-4 pb-3 space-y-2.5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Shield className="h-4 w-4 text-emerald-500" />
          Preventive Care
          {items.length > 0 && (
            <Badge className="text-[10px] font-bold px-1.5 py-0 bg-emerald-100 text-emerald-800 border border-emerald-200">
              {items.length}
            </Badge>
          )}
        </div>

        {sorted.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-muted-foreground">
            <Shield className="h-4 w-4 text-emerald-500" />
            <span className="text-xs">All preventive care up to date</span>
          </div>
        ) : (
          <div className="relative pl-4 space-y-2">
            <div className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-border" />
            {sorted.map((item, idx) => {
              const status = dueStatusConfig[item.due_status];
              return (
                <div key={`${item.member_id}-${item.category}-${idx}`} className="relative">
                  <div
                    className={`absolute -left-4 top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background ${status.dotClass}`}
                  />
                  <div
                    className={`flex items-start justify-between gap-2 rounded-lg border px-2.5 py-2 ${status.bg}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <p className="text-xs font-semibold truncate">{item.recommendation}</p>
                        <Badge
                          className={`text-[10px] font-bold shrink-0 px-1 py-0 ${priorityConfig[item.priority]}`}
                        >
                          {item.priority}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[11px] text-muted-foreground">
                          {item.member_name}
                        </span>
                        <Badge className={`text-[10px] font-bold px-1 py-0 ${status.badgeClass}`}>
                          <Clock className="h-2 w-2 mr-0.5" />
                          {status.label}
                        </Badge>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onSetReminder(item.member_id, item.recommendation)}
                      className="shrink-0 p-0.5 h-auto text-muted-foreground hover:text-foreground"
                    >
                      <CalendarPlus className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
