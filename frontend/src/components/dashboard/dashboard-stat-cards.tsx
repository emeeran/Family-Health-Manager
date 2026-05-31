import { memo } from "react";
import { Users, FileText, Stethoscope, Activity, AlertTriangle, Syringe } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { scoreColor } from "@/components/ui/health-score-ring";

interface StatCardsProps {
  activeCount: number;
  recordsCount: number;
  providersCount: number;
  avgScore: number;
  scoresLoading: boolean;
  vacStatus?: { total_vaccinations: number; overdue_count: number } | null;
  riskSummary?: { high_risk_members: number; moderate_risk_members: number } | null;
}

export const DashboardStatCards = memo(function DashboardStatCards({
  activeCount,
  recordsCount,
  providersCount,
  avgScore,
  scoresLoading,
  vacStatus,
  riskSummary,
}: StatCardsProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground font-medium">Members</p>
            <Users className="h-4 w-4 text-muted-foreground/40" />
          </div>
          <p className="text-2xl font-bold mt-1">{activeCount}</p>
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground font-medium">Records</p>
            <FileText className="h-4 w-4 text-muted-foreground/40" />
          </div>
          <p className="text-2xl font-bold mt-1">{recordsCount}</p>
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground font-medium">Providers</p>
            <Stethoscope className="h-4 w-4 text-muted-foreground/40" />
          </div>
          <p className="text-2xl font-bold mt-1">{providersCount}</p>
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground font-medium">Avg Score</p>
            <Activity className="h-4 w-4 text-muted-foreground/40" />
          </div>
          <p className="text-2xl font-bold mt-1" style={{ color: scoreColor(avgScore) }}>
            {!scoresLoading && avgScore > 0 ? avgScore : "--"}
          </p>
        </CardContent>
      </Card>
      {vacStatus && vacStatus.total_vaccinations > 0 && (
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground font-medium">Vaccines</p>
              <Syringe className="h-4 w-4 text-muted-foreground/40" />
            </div>
            <p className="text-2xl font-bold mt-1">{vacStatus.total_vaccinations}</p>
            {vacStatus.overdue_count > 0 && (
              <p className="text-[10px] text-amber-600 font-medium">
                {vacStatus.overdue_count} overdue
              </p>
            )}
          </CardContent>
        </Card>
      )}
      {riskSummary &&
        (riskSummary.high_risk_members > 0 || riskSummary.moderate_risk_members > 0) && (
          <Card className="shadow-none border-red-200 bg-red-50/50">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-red-600 font-medium">Risk Alerts</p>
                <AlertTriangle className="h-4 w-4 text-red-400" />
              </div>
              <p className="text-2xl font-bold mt-1 text-red-700">
                {riskSummary.high_risk_members + riskSummary.moderate_risk_members}
              </p>
            </CardContent>
          </Card>
        )}
    </div>
  );
});
