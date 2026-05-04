import React, { Suspense } from "react";
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
        <ResponsiveContainer width="100%" height={320}>
          <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
            <PolarGrid stroke="currentColor" strokeOpacity={0.1} />
            <PolarAngleAxis
              dataKey="axis"
              tick={{ fontSize: 11, fill: "currentColor", opacity: 0.6 }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 9, fill: "currentColor", opacity: 0.3 }}
              tickCount={5}
            />
            {members.map((m, i) => (
              <Radar
                key={m.name}
                name={m.name}
                dataKey={m.name}
                stroke={m.color}
                fill={m.color}
                fillOpacity={0.12}
                strokeWidth={2}
              />
            ))}
            <Tooltip
              contentStyle={{
                borderRadius: "12px",
                border: "1px solid hsl(var(--border))",
                background: "hsl(var(--popover) / 0.95)",
                backdropFilter: "blur(8px)",
                fontSize: "12px",
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
              iconType="circle"
              iconSize={8}
            />
          </RadarChart>
        </ResponsiveContainer>
      );
    },
  }))
);

export function FamilyComparisonChart({ scores }: FamilyComparisonChartProps) {
  const membersWithScores = scores.filter((s) => s.health_score > 0);

  if (membersWithScores.length < 2) {
    return (
      <Card className="overflow-hidden shadow-sm">
        <div className="h-1.5 bg-gradient-to-r from-indigo-400 to-blue-500" />
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10">
              <Users className="h-4 w-4 text-indigo-600" />
            </div>
            Family Comparison
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-2 py-8 text-foreground/70">
            <Users className="h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm font-medium">
              Add at least 2 members with health scores to compare
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Build radar data: each axis is a score_breakdown key
  const chartData = RADAR_KEYS.map((key) => {
    const row: Record<string, string | number> = { axis: RADAR_LABELS[key] };
    for (const member of membersWithScores) {
      const breakdown = member.score_breakdown[key];
      if (breakdown) {
        row[`${member.first_name} ${member.last_name}`] = Math.round(
          (breakdown.score / breakdown.max) * 100
        );
      } else {
        row[`${member.first_name} ${member.last_name}`] = 0;
      }
    }
    return row;
  });

  const memberEntries = membersWithScores.map((m, i) => ({
    name: `${m.first_name} ${m.last_name}`,
    color: MEMBER_COLORS[i % MEMBER_COLORS.length],
  }));

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="h-1.5 bg-gradient-to-r from-indigo-400 to-blue-500" />
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10">
            <Users className="h-4 w-4 text-indigo-600" />
          </div>
          Family Comparison
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-8">
              <Skeleton className="h-[320px] w-full" />
            </div>
          }
        >
          <LazyRadarChart data={chartData} members={memberEntries} />
        </Suspense>
      </CardContent>
    </Card>
  );
}
