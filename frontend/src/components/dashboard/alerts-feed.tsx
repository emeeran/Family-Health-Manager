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
    badgeClass: "bg-red-100 text-red-800 border border-red-200",
    icon: AlertTriangle,
  },
  warning: {
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    badgeClass: "bg-amber-100 text-amber-800 border border-amber-200",
    icon: AlertTriangle,
  },
  info: {
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badgeClass: "bg-blue-100 text-blue-800 border border-blue-200",
    icon: Bell,
  },
} as const;

export function AlertsFeed({ alerts, onDismiss }: AlertsFeedProps) {
  const displayed = alerts.slice(0, 5);
  const criticalCount = alerts.filter((a) => a.severity === "critical").length;

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="text-base font-semibold flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-red-500/10">
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </div>
          Health Alerts
          {alerts.length > 0 && (
            <Badge
              className={`text-[11px] font-bold px-2 py-0.5 ${severityConfig[alerts[0]?.severity ?? "info"].badgeClass}`}
            >
              {alerts.length}
            </Badge>
          )}
          {criticalCount > 0 && (
            <span className="text-xs text-red-600 font-semibold">{criticalCount} critical</span>
          )}
        </div>
      </div>
      <CardContent>
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
            <CheckCircle2 className="h-8 w-8 text-emerald-500" />
            <p className="text-sm font-medium">All clear — no active health alerts</p>
          </div>
        ) : (
          <div className="space-y-2">
            {displayed.map((alert) => {
              const config = severityConfig[alert.severity];
              const Icon = config.icon;
              return (
                <div
                  key={alert.id}
                  className={`flex items-start gap-3 rounded-xl border px-4 py-3 ${config.bg} ${config.border} transition-colors`}
                >
                  <Icon className={`h-5 w-5 shrink-0 mt-0.5 ${config.color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold truncate">{alert.title}</p>
                      <Badge
                        className={`text-[11px] font-bold shrink-0 px-2 py-0.5 ${config.badgeClass}`}
                      >
                        {alert.severity}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      {alert.member_name}
                      <span className="mx-1.5">&middot;</span>
                      {formatRelativeTime(alert.created_at)}
                    </p>
                    {alert.message && (
                      <p className="text-sm text-foreground/70 mt-1">{alert.message}</p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDismiss(alert.id)}
                    className="shrink-0 text-muted-foreground hover:text-foreground p-1 h-auto"
                  >
                    <X className="h-4 w-4" />
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
