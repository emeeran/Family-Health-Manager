import { memo } from "react";
import { Link } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface FamilyStripProps {
  members: FamilyMemberResponse[];
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

export const FamilyStrip = memo(function FamilyStrip({ members }: FamilyStripProps) {
  if (members.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Family
        </p>
        <Link to="/people" className="text-xs text-primary hover:underline underline-offset-2">
          View all
        </Link>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-none">
        {members.map((member) => (
          <Link
            key={member.id}
            to={`/people/${member.id}`}
            className="flex flex-col items-center gap-1.5 shrink-0 group"
          >
            <div className="relative">
              <Avatar className="h-11 w-11 ring-2 ring-background shadow-sm group-hover:ring-primary/30 transition-all">
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
    </div>
  );
});
