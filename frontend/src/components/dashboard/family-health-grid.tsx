import { memo } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { HealthScoreRing } from "@/components/ui/health-score-ring";
import { RELATIONSHIP_LABELS } from "@/lib/constants";
import { formatAge } from "@/lib/utils";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface FamilyHealthGridProps {
  activeMembers: FamilyMemberResponse[];
  memberScores: Record<
    string,
    { score: number; medications: number; conditions: number; riskLevel: string }
  >;
  scoresLoading: boolean;
  memberRecordCounts: Record<string, number>;
}

export const FamilyHealthGrid = memo(function FamilyHealthGrid({
  activeMembers,
  memberScores,
  scoresLoading,
  memberRecordCounts,
}: FamilyHealthGridProps) {
  return (
    <div>
      <h2 className="text-sm font-semibold mb-3">Family Health</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {activeMembers.map((member) => {
          const scoreData = memberScores[member.id];
          const fullName = `${member.first_name} ${member.last_name}`;
          const recCount = memberRecordCounts[member.id] || 0;
          const age = formatAge(member.date_of_birth);
          const riskLevel = scoreData?.riskLevel;
          const isHighRisk = riskLevel === "high" || riskLevel === "moderate";

          return (
            <Link
              key={member.id}
              to={`/members/${member.id}`}
              className="group rounded-lg border bg-card p-3.5 hover:shadow-md transition-all"
            >
              <div className="flex items-center gap-3">
                {scoresLoading ? (
                  <Skeleton className="h-[56px] w-[56px] rounded-full shrink-0" />
                ) : scoreData ? (
                  <HealthScoreRing score={scoreData.score} size={56} />
                ) : (
                  <div className="flex h-[56px] w-[56px] items-center justify-center rounded-full bg-muted/50 shrink-0">
                    <span className="text-sm font-bold text-muted-foreground">--</span>
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-semibold truncate">{fullName}</p>
                    {isHighRisk && (
                      <span
                        className={`inline-block h-1.5 w-1.5 rounded-full ${riskLevel === "high" ? "bg-red-500" : "bg-amber-500"}`}
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-muted-foreground">
                    <span>{RELATIONSHIP_LABELS[member.relationship]}</span>
                    {age && (
                      <>
                        <span className="opacity-30">·</span>
                        <span>{age}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 mt-2.5 flex-wrap">
                {member.blood_group && (
                  <span className="text-[10px] font-semibold text-red-600 bg-red-50 px-1.5 py-0.5 rounded">
                    {member.blood_group}
                  </span>
                )}
                {member.bmi && (
                  <span className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                    BMI {member.bmi.toFixed(1)}
                  </span>
                )}
                {recCount > 0 && (
                  <span className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                    {recCount} recs
                  </span>
                )}
                {scoreData && scoreData.medications > 0 && (
                  <span className="text-[10px] text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded">
                    {scoreData.medications} meds
                  </span>
                )}
                {member.allergies && member.allergies.length > 0 && (
                  <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                    {member.allergies.length} allerg{member.allergies.length !== 1 ? "ies" : "y"}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
        <Link
          to="/members/new"
          className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border/50 py-8 hover:border-primary/30 transition-colors group"
        >
          <Plus className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
          <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">
            Add Member
          </span>
        </Link>
      </div>
    </div>
  );
});
