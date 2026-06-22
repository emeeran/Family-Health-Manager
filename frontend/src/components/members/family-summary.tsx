import { useMemo, memo } from "react";
import { Users, Activity, Heart, AlertTriangle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { HealthScoreRing } from "@/components/ui/health-score-ring";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface ScoreData {
  score: number;
  medications: number;
  conditions: number;
}

interface FamilySummaryBarProps {
  activeCount: number;
  scores: Record<string, ScoreData>;
  members: FamilyMemberResponse[];
  loading: boolean;
}

export const FamilySummaryBar = memo(function FamilySummaryBar({
  activeCount,
  scores,
  members,
  loading,
}: FamilySummaryBarProps) {
  const stats = useMemo(() => {
    const scoreValues = Object.values(scores);
    const avgScore = scoreValues.length
      ? Math.round(scoreValues.reduce((s, d) => s + d.score, 0) / scoreValues.length)
      : 0;
    const totalConditions = scoreValues.reduce((s, d) => s + d.conditions, 0);
    const severeAllergyCount = members.filter((m) =>
      m.allergies?.some((a) => a.severity === "severe")
    ).length;
    return { avgScore, totalConditions, severeAllergyCount };
  }, [scores, members]);

  const cards = [
    {
      icon: <Users className="h-4 w-4 text-blue-500" />,
      label: "Members",
      value: activeCount,
    },
    {
      icon: <Activity className="h-4 w-4 text-green-500" />,
      label: "Avg Score",
      value: loading ? null : stats.avgScore,
      extra:
        !loading && stats.avgScore > 0 ? (
          <HealthScoreRing score={stats.avgScore} size={28} />
        ) : null,
    },
    {
      icon: <Heart className="h-4 w-4 text-rose-500" />,
      label: "Conditions",
      value: loading ? null : stats.totalConditions,
    },
    {
      icon: <AlertTriangle className="h-4 w-4 text-amber-500" />,
      label: "Severe Allergies",
      value: stats.severeAllergyCount,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div
          key={c.label}
          className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3 shadow-sm select-none"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted/50">
            {c.icon}
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground truncate">{c.label}</p>
            {c.value === null ? (
              <Skeleton className="h-5 w-8 mt-0.5" />
            ) : (
              <div className="flex items-center gap-1.5">
                <p className="text-lg font-bold leading-none">{c.value}</p>
                {c.extra}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
});
