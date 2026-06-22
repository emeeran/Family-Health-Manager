import { memo } from "react";
import { AlertTriangle, Info, X } from "lucide-react";
import type { DashboardAlert } from "@/lib/types/dashboard";

interface AlertStripProps {
  alerts: DashboardAlert[];
  onDismiss: (id: string) => void;
}

function getAlertStyles(severity: string) {
  switch (severity) {
    case "critical":
      return "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800";
    case "warning":
      return "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800";
    case "info":
      return "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800";
    default:
      return "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800";
  }
}

function getAlertIconColor(severity: string) {
  switch (severity) {
    case "critical":
      return "text-red-600 dark:text-red-400";
    case "warning":
      return "text-amber-600 dark:text-amber-400";
    case "info":
      return "text-blue-600 dark:text-blue-400";
    default:
      return "text-amber-600 dark:text-amber-400";
  }
}

function getAlertTextColor(severity: string) {
  switch (severity) {
    case "critical":
      return "text-red-800 dark:text-red-200";
    case "warning":
      return "text-amber-800 dark:text-amber-200";
    case "info":
      return "text-blue-800 dark:text-blue-200";
    default:
      return "text-amber-800 dark:text-amber-200";
  }
}

function getAlertDismissColor(severity: string) {
  switch (severity) {
    case "critical":
      return "text-red-600 dark:text-red-400";
    case "warning":
      return "text-amber-600 dark:text-amber-400";
    case "info":
      return "text-blue-600 dark:text-blue-400";
    default:
      return "text-amber-600 dark:text-amber-400";
  }
}

export const AlertStrip = memo(function AlertStrip({ alerts, onDismiss }: AlertStripProps) {
  if (alerts.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
      {alerts.map((alert, index) => (
        <div
          key={alert.id}
          className={`animate-slide-in flex items-center gap-2 shrink-0 rounded-full border px-3 py-1.5 ${getAlertStyles(alert.severity)}`}
          style={{ animationDelay: `${index * 80}ms` }}
        >
          {alert.severity === "info" ? (
            <Info className={`h-3.5 w-3.5 ${getAlertIconColor(alert.severity)} shrink-0`} />
          ) : (
            <AlertTriangle
              className={`h-3.5 w-3.5 ${getAlertIconColor(alert.severity)} shrink-0`}
            />
          )}
          <span
            className={`text-xs font-medium ${getAlertTextColor(alert.severity)} whitespace-nowrap`}
          >
            {alert.title}
          </span>
          <button
            onClick={() => onDismiss(alert.id)}
            className={`shrink-0 p-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10 transition-colors ${getAlertDismissColor(alert.severity)}`}
            aria-label="Dismiss alert"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
});
