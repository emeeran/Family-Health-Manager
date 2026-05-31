import React, { Suspense, memo } from "react";
import { Users } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MemberScore } from "@/lib/types/dashboard";

interface FamilyComparisonChartProps {
  scores: MemberScore[];
}

const MEMBER_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6", "#14b8a6"];
const RADAR_KEYS = ["bmi", "conditions", "labs", "meds", "profile", "recency"] as const;
const RADAR_LABELS: Record<string, string> = {
  bmi: "BMI",
  conditions: "Conditions",
  labs: "Labs",
  meds: "Meds",
  profile: "Profile",
  recency: "Recency",
};

const LazyRadarChart = React.lazy(() =>
  import("recharts").then((mod) => ({
    default: ({
      data,
      members,
    }: {
      data: Record<string, string | number>[];
      members: { name: string; color: string }[];
    }) => {
      const {
        RadarChart,
        PolarGrid,
        PolarAngleAxis,
        PolarRadiusAxis,
        Radar,
        Legend,
        ResponsiveContainer,
        Tooltip,
      } = mod;
      return (
        <ResponsiveContainer width="100%" height={280}>
          <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
            <PolarGrid stroke="currentColor" strokeOpacity={0.1} />
            <PolarAngleAxis
              dataKey="axis"
              tick={{ fontSize: 10, fill: "currentColor", opacity: 0.5 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 8, fill: "currentColor", opacity: 0.25 }}
              tickCount={5}
            />
            {members.map((m) => (
              <Radar
                key={m.name}
                name={m.name}
                dataKey={m.name}
                stroke={m.color}
                fill={m.color}
                fillOpacity={0.1}
                strokeWidth={1.5}
              />
            ))}
            <Tooltip
              contentStyle={{
                borderRadius: "8px",
                border: "1px solid hsl(var(--border))",
                background: "hsl(var(--popover) / 0.95)",
                fontSize: "11px",
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", paddingTop: "4px" }}
              iconType="circle"
              iconSize={6}
            />
          </RadarChart>
        </ResponsiveContainer>
      );
    },
  }))
);

export const FamilyComparisonChart = memo(function FamilyComparisonChart({
  scores,
}: FamilyComparisonChartProps) {
  const membersWithScores = scores.filter((s) => s.health_score > 0);

  if (membersWithScores.length < 2) return null;

  const chartData = RADAR_KEYS.map((key) => {
    const row: Record<string, string | number> = { axis: RADAR_LABELS[key] };
    for (const member of membersWithScores) {
      const breakdown = member.score_breakdown[key];
      row[`${member.first_name} ${member.last_name}`] = breakdown
        ? Math.round((breakdown.score / breakdown.max) * 100)
        : 0;
    }
    return row;
  });

  const memberEntries = membersWithScores.map((m, i) => ({
    name: `${m.first_name} ${m.last_name}`,
    color: MEMBER_COLORS[i % MEMBER_COLORS.length],
  }));

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Users className="h-4 w-4 text-indigo-500" />
          Family Comparison
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-6">
              <Skeleton className="h-[280px] w-full" />
            </div>
          }
        >
          <LazyRadarChart data={chartData} members={memberEntries} />
        </Suspense>
      </CardContent>
    </Card>
  );
});
