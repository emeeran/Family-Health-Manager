import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, AlertCircle, Info, X, CheckCircle } from "lucide-react";
import { listHealthAlerts, dismissHealthAlert } from "@/lib/api/health-alerts";
import { toast } from "sonner";
import type { HealthAlertResponse, AlertSeverity } from "@/lib/types/health-alert";

const SEVERITY_CONFIG: Record<
  AlertSeverity,
  { icon: typeof AlertTriangle; color: string; bg: string; border: string }
> = {
  critical: {
    icon: AlertCircle,
    color: "text-red-600",
    bg: "bg-red-50 dark:bg-red-950/30",
    border: "border-red-200 dark:border-red-900",
  },
  warning: {
    icon: AlertTriangle,
    color: "text-amber-600",
    bg: "bg-amber-50 dark:bg-amber-950/30",
    border: "border-amber-200 dark:border-amber-900",
  },
  info: {
    icon: Info,
    color: "text-blue-600",
    bg: "bg-blue-50 dark:bg-blue-950/30",
    border: "border-blue-200 dark:border-blue-900",
  },
};

export function AlertsContent() {
  const [alerts, setAlerts] = useState<HealthAlertResponse[]>([]);
  const [loading, setLoading] = useState(true);

  async function fetchAlerts() {
    try {
      const data = await listHealthAlerts({ dismissed: false });
      setAlerts(data);
    } catch {
      toast.error("Failed to load health alerts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAlerts();
  }, []);

  async function handleDismiss(alertId: string) {
    try {
      await dismissHealthAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
      toast.success("Alert dismissed");
    } catch {
      toast.error("Failed to dismiss alert");
    }
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
        <h2 className="text-lg font-semibold">All Clear</h2>
        <p className="text-sm text-muted-foreground mt-1">No active health alerts right now.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {alerts.length} active alert{alerts.length !== 1 ? "s" : ""}
        </p>
      </div>
      {alerts.map((alert) => {
        const config = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
        const Icon = config.icon;
        return (
          <Card key={alert.id} className={`${config.bg} ${config.border} border`}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <Icon className={`h-5 w-5 mt-0.5 ${config.color} shrink-0`} />
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold">{alert.title}</h3>
                      <Badge variant="outline" className="text-xs capitalize">
                        {alert.severity}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{alert.message}</p>
                    <div className="flex items-center gap-3 pt-1">
                      {alert.test_name && (
                        <span className="text-xs font-medium">
                          {alert.test_name}: {alert.value}
                        </span>
                      )}
                      {alert.reference && (
                        <span className="text-xs text-muted-foreground">
                          Ref: {alert.reference}
                        </span>
                      )}
                      {alert.record_id && (
                        <Link
                          to={`/members/${alert.family_member_id}/records/${alert.record_id}`}
                          className="text-xs text-blue-500 hover:underline"
                        >
                          View Record
                        </Link>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 shrink-0"
                  onClick={() => handleDismiss(alert.id)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
