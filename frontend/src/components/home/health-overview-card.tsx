import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, Syringe, AlertTriangle, Pill } from "lucide-react";
import type { DashboardSummary } from "@/lib/types/dashboard";

interface HealthOverviewCardProps {
  summary: DashboardSummary;
}

export const HealthOverviewCard = memo(function HealthOverviewCard({
  summary,
}: HealthOverviewCardProps) {
  const { record_activity, vaccination_status, risk_summary, medication_summary } = summary;

  const typeColors: Record<string, string> = {
    doctor_visit: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    lab_report: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    prescription: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400",
    vitals: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  };

  const typeLabels: Record<string, string> = {
    doctor_visit: "Visits",
    lab_report: "Labs",
    prescription: "Rx",
    vitals: "Vitals",
  };

  return (
    <Card className="border-0 shadow-none bg-gradient-to-br from-muted/40 to-muted/20">
      <CardHeader className="pb-2 pt-3 px-3">
        <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Health Overview
        </CardTitle>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        <div className="grid grid-cols-2 gap-3">
          {/* Records this month */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] text-muted-foreground">Records (30d)</span>
            </div>
            <p className="text-xl font-bold leading-none">
              {record_activity?.total_last_30_days ?? 0}
            </p>
            {record_activity?.by_type && Object.keys(record_activity.by_type).length > 0 && (
              <div className="flex flex-wrap gap-1">
                {Object.entries(record_activity.by_type)
                  .filter(([, count]) => count > 0)
                  .slice(0, 3)
                  .map(([type, count]) => (
                    <Badge
                      key={type}
                      variant="outline"
                      className={`text-[9px] px-1 py-0 h-4 ${typeColors[type] || ""}`}
                    >
                      {typeLabels[type] || type} {count}
                    </Badge>
                  ))}
              </div>
            )}
          </div>

          {/* Vaccinations */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <Syringe className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] text-muted-foreground">Vaccinations</span>
            </div>
            <p className="text-xl font-bold leading-none">
              {vaccination_status?.total_vaccinations ?? 0}
            </p>
            {(vaccination_status?.overdue_count ?? 0) > 0 && (
              <Badge
                variant="outline"
                className="text-[9px] px-1 py-0 h-4 bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
              >
                <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
                {vaccination_status.overdue_count} overdue
              </Badge>
            )}
          </div>

          {/* Risk summary */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] text-muted-foreground">Risk Levels</span>
            </div>
            <div className="flex items-center gap-2 pt-1">
              {[
                {
                  color: "bg-red-500",
                  count: risk_summary?.high_risk_members ?? 0,
                  label: "high",
                },
                {
                  color: "bg-amber-500",
                  count: risk_summary?.moderate_risk_members ?? 0,
                  label: "mod",
                },
                {
                  color: "bg-green-500",
                  count: risk_summary?.low_risk_members ?? 0,
                  label: "low",
                },
              ].map((level) => (
                <div key={level.label} className="flex items-center gap-1">
                  <span className={`inline-block h-2 w-2 rounded-full ${level.color}`} />
                  <span className="text-xs font-medium">{level.count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Medications */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <Pill className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[11px] text-muted-foreground">Medications</span>
            </div>
            <p className="text-xl font-bold leading-none">
              {medication_summary?.total_active_medications ?? 0}
            </p>
            {(medication_summary?.refill_reminders?.length ?? 0) > 0 && (
              <Badge
                variant="outline"
                className="text-[9px] px-1 py-0 h-4 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
              >
                {medication_summary!.refill_reminders.length} refill
                {medication_summary!.refill_reminders.length !== 1 ? "s" : ""}
              </Badge>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
});
