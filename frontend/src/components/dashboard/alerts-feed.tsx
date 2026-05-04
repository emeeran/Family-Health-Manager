import { AlertTriangle, CheckCircle2, X, Bell } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DashboardAlert } from "@/lib/types/dashboard";

interface AlertsFeedProps {
  alerts: DashboardAlert[];
  onDismiss: (id: string) => void;
}

function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const absDays = Math.abs(Math.round(diffMs / (1000 * 60 * 60 * 24)));
  if (absDays === 0) {
    const hours = Math.abs(Math.round(diffMs / (1000 * 60 * 60)));
    if (hours === 0) {
      const mins = Math.abs(Math.round(diffMs / (1000 * 60)));
      return mins <= 1 ? "Just now" : `${mins}m ago`;
    }
    return hours === 1 ? "1h ago" : `${hours}h ago`;
  }
  if (absDays === 1) return "Yesterday";
  return `${absDays}d ago`;
}

const severityConfig = {
  critical: {
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    icon: AlertTriangle,
  },
  warning: {
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    icon: AlertTriangle,
  },
  info: { color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200", icon: Bell },
} as const;

export function AlertsFeed({ alerts, onDismiss }: AlertsFeedProps) {
  const displayed = alerts.slice(0, 5);
  const criticalCount = alerts.filter((a) => a.severity === "critical").length;

  return (
    <Card className="shadow-sm">
      <CardContent className="pt-4 pb-3 space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-red-500" />
          Alerts
          <Badge className="text-[10px] font-bold px-1.5 py-0 bg-red-100 text-red-800 border border-red-200">
            {alerts.length}
          </Badge>
          {criticalCount > 0 && (
            <span className="text-xs text-red-600 font-semibold">{criticalCount} critical</span>
          )}
        </div>
        {displayed.length === 0 ? (
          <div className="flex items-center gap-2 py-3 text-muted-foreground">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            <span className="text-xs">No active alerts</span>
          </div>
        ) : (
          <div className="space-y-1.5">
            {displayed.map((alert) => {
              const config = severityConfig[alert.severity];
              const Icon = config.icon;
              return (
                <div
                  key={alert.id}
                  className={`flex items-start gap-2.5 rounded-lg border px-3 py-2 ${config.bg} ${config.border}`}
                >
                  <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${config.color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold truncate">{alert.title}</span>
                      <span className={`text-[10px] font-bold uppercase ${config.color}`}>
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {alert.member_name}
                      <span className="mx-1">&middot;</span>
                      {formatRelativeTime(alert.created_at)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDismiss(alert.id)}
                    className="shrink-0 p-0.5 h-auto text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
