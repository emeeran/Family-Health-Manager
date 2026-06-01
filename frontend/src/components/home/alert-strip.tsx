import { memo } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { DashboardAlert } from "@/lib/types/dashboard";

interface AlertStripProps {
  alerts: DashboardAlert[];
  onDismiss: (id: string) => void;
}

export const AlertStrip = memo(function AlertStrip({ alerts, onDismiss }: AlertStripProps) {
  if (alerts.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className="flex items-center gap-2 shrink-0 rounded-full border border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 px-3 py-1.5"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
          <span className="text-xs font-medium text-amber-800 dark:text-amber-200 whitespace-nowrap">
            {alert.title}
          </span>
          <button
            onClick={() => onDismiss(alert.id)}
            className="shrink-0 text-amber-600 dark:text-amber-400 hover:text-foreground transition-colors"
            aria-label="Dismiss alert"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  );
});
