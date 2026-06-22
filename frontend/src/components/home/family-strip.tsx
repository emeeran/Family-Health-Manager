import { memo } from "react";
import { Link } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { HealthScoreRing } from "@/components/ui/health-score-ring";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { MemberScore } from "@/lib/types/dashboard";

interface FamilyStripProps {
  members: FamilyMemberResponse[];
  scores?: MemberScore[];
  layout?: "horizontal" | "vertical";
}

function getInitials(firstName: string, lastName: string) {
  return `${firstName[0]}${lastName[0]}`.toUpperCase();
}

function getRelationshipColor(relationship: string) {
  const colors: Record<string, string> = {
    self: "bg-blue-500",
    spouse: "bg-pink-500",
    wife: "bg-pink-500",
    husband: "bg-blue-500",
    son: "bg-emerald-500",
    daughter: "bg-purple-500",
    parent: "bg-amber-500",
    default: "bg-primary",
  };
  return colors[relationship] || colors.default;
}

function scoreLabel(score: number): string {
  if (score >= 70) return "Good";
  if (score >= 40) return "Needs attention";
  return "At risk";
}

export const FamilyStrip = memo(function FamilyStrip({
  members,
  scores,
  layout,
}: FamilyStripProps) {
  if (members.length === 0) return null;

  // Use vertical layout when inside sidebar column (scores provided or explicit)
  const isVertical = layout === "vertical" || !!scores;

  // Build score lookup
  const scoreMap = new Map<string, MemberScore>();
  if (scores) {
    for (const s of scores) scoreMap.set(s.member_id, s);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="section-label">Family</p>
        <Link to="/people" className="text-xs text-primary hover:underline underline-offset-2">
          View all
        </Link>
      </div>
      <div className="bg-gradient-to-r from-[var(--brand-primary)]/[0.03] to-[var(--brand-accent)]/[0.03] rounded-xl px-3 py-3">
        {isVertical ? (
          <div className="space-y-2">
            {members.map((member) => {
              const score = scoreMap.get(member.id);
              return (
                <Link
                  key={member.id}
                  to={`/people/${member.id}`}
                  className="flex items-center gap-3 group"
                >
                  <Avatar className="h-9 w-9 ring-2 ring-background shadow-sm group-hover:ring-[var(--brand-accent)]/30 transition-all shrink-0">
                    <AvatarFallback
                      className={`text-[10px] font-bold text-white ${getRelationshipColor(member.relationship)}`}
                    >
                      {getInitials(member.first_name, member.last_name)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors flex-1 min-w-0 truncate">
                    {member.first_name}
                  </span>
                  {score && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger className="shrink-0">
                          <HealthScoreRing score={score.health_score} size={36} strokeWidth={2.5} />
                        </TooltipTrigger>
                        <TooltipContent>
                          Score: {score.health_score}/100 — {scoreLabel(score.health_score)}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-none">
            {members.map((member) => (
              <Link
                key={member.id}
                to={`/people/${member.id}`}
                className="flex flex-col items-center gap-1.5 shrink-0 group"
              >
                <div className="relative">
                  <Avatar className="h-11 w-11 ring-2 ring-background shadow-sm group-hover:ring-[var(--brand-accent)]/30 transition-all">
                    <AvatarFallback
                      className={`text-xs font-bold text-white ${getRelationshipColor(member.relationship)}`}
                    >
                      {getInitials(member.first_name, member.last_name)}
                    </AvatarFallback>
                  </Avatar>
                </div>
                <span className="text-[10px] font-medium text-muted-foreground group-hover:text-foreground transition-colors max-w-[56px] truncate text-center">
                  {member.first_name}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
