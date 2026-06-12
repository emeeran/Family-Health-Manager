import { memo, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  FileText,
  Calendar,
  Pencil,
  Trash2,
  Droplets,
  Activity,
  Heart,
  Pill,
  AlertTriangle,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { RELATIONSHIP_LABELS, GENDER_LABELS, BMI_CATEGORY_COLORS } from "@/lib/constants";
import { HealthScoreRing, scoreTextColor } from "@/components/ui/health-score-ring";
import { getMemberDetail } from "@/lib/api/members";
import { computeAge } from "@/lib/utils";
import type { FamilyMemberResponse } from "@/lib/types/member";

/* ── Color system ── */

const REL_COLORS: Record<string, { bg: string; gradient: string; text: string; ring: string }> = {
  self: {
    bg: "bg-blue-500/10",
    gradient: "from-blue-500 to-indigo-600",
    text: "text-blue-600 dark:text-blue-400",
    ring: "ring-blue-500/20",
  },
  wife: {
    bg: "bg-rose-500/10",
    gradient: "from-rose-500 to-pink-600",
    text: "text-rose-600 dark:text-rose-400",
    ring: "ring-rose-500/20",
  },
  spouse: {
    bg: "bg-rose-500/10",
    gradient: "from-rose-500 to-pink-600",
    text: "text-rose-600 dark:text-rose-400",
    ring: "ring-rose-500/20",
  },
  son: {
    bg: "bg-emerald-500/10",
    gradient: "from-emerald-500 to-teal-600",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/20",
  },
  daughter: {
    bg: "bg-emerald-500/10",
    gradient: "from-emerald-500 to-teal-600",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/20",
  },
  grand_son: {
    bg: "bg-emerald-500/10",
    gradient: "from-emerald-500 to-teal-600",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/20",
  },
  grand_daughter: {
    bg: "bg-emerald-500/10",
    gradient: "from-emerald-500 to-teal-600",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-500/20",
  },
  parent: {
    bg: "bg-amber-500/10",
    gradient: "from-amber-500 to-orange-600",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-500/20",
  },
  daughter_in_law: {
    bg: "bg-amber-500/10",
    gradient: "from-amber-500 to-orange-600",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-500/20",
  },
  son_in_law: {
    bg: "bg-amber-500/10",
    gradient: "from-amber-500 to-orange-600",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-500/20",
  },
  sibling: {
    bg: "bg-violet-500/10",
    gradient: "from-violet-500 to-purple-600",
    text: "text-violet-600 dark:text-violet-400",
    ring: "ring-violet-500/20",
  },
  others: {
    bg: "bg-gray-500/10",
    gradient: "from-gray-500 to-slate-600",
    text: "text-gray-600 dark:text-gray-400",
    ring: "ring-gray-500/20",
  },
};

function getRelColor(relationship: string) {
  return REL_COLORS[relationship] || REL_COLORS.others;
}

function getInitials(first: string, last: string): string {
  return (first[0] + (last ? last[0] : "")).toUpperCase();
}

function allergySeverityColor(allergies: FamilyMemberResponse["allergies"]): string | null {
  if (!allergies || allergies.length === 0) return null;
  if (allergies.some((a) => a.severity === "severe")) return "text-red-500";
  if (allergies.some((a) => a.severity === "moderate")) return "text-amber-500";
  return "text-emerald-500";
}

interface ScoreData {
  score: number;
  medications: number;
  conditions: number;
}

/* ── Tooltip action link ── */

export const TooltipActionLink = memo(function TooltipActionLink({
  to,
  icon,
  label,
  compact,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  compact?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger>
        <Link
          to={to}
          className={`inline-flex items-center gap-1 rounded-lg text-muted-foreground/60 hover:text-foreground hover:bg-muted/50 transition-all duration-200 ${compact ? "p-2" : "px-2 py-1.5 text-xs"}`}
          aria-label={label}
        >
          {icon}
          {!compact && <span>{label}</span>}
        </Link>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
});

/* ── Grid card ── */

interface MemberCardProps {
  member: FamilyMemberResponse;
  scoreData?: ScoreData;
  onDelete: (id: string) => void;
}

export const MemberCard = memo(function MemberCard({
  member,
  scoreData,
  onDelete,
}: MemberCardProps) {
  const color = getRelColor(member.relationship);
  const fullName = `${member.first_name} ${member.last_name}`;
  const initials = getInitials(member.first_name, member.last_name);
  const age = computeAge(member.date_of_birth);
  const genderLabel = GENDER_LABELS[member.gender] || member.gender;
  const allergyCount = member.allergies?.length || 0;
  const allergyColor = allergySeverityColor(member.allergies);
  const bmiColor = member.bmi_category ? BMI_CATEGORY_COLORS[member.bmi_category] : "";
  const medCount = scoreData?.medications ?? 0;
  const condCount = scoreData?.conditions ?? 0;

  const handleMouseEnter = useCallback(() => {
    // Prefetch aggregated member detail on hover for instant page load
    getMemberDetail(member.id).catch(() => {});
  }, [member.id]);

  return (
    <Card
      className="group relative overflow-hidden hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
      onMouseEnter={handleMouseEnter}
    >
      {/* Top gradient accent stripe */}
      <div
        className={`h-1 w-full bg-gradient-to-r ${color.gradient} opacity-60 group-hover:opacity-100 transition-opacity`}
      />

      <div className="px-4 pt-3 pb-3">
        {/* Row 1: Health score ring + name + relationship */}
        <div className="flex items-start gap-3">
          {/* Health Score Ring */}
          {scoreData !== undefined ? (
            <HealthScoreRing score={scoreData.score} initials={initials} size={48} />
          ) : (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-muted/50">
              <Skeleton className="h-12 w-12 rounded-xl" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <Link
                to={`/people/${member.id}`}
                className="text-base font-bold text-foreground hover:text-(--brand-primary) transition-colors truncate block"
              >
                {fullName}
              </Link>
              <span
                className={`shrink-0 inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${color.text} ${color.bg}`}
              >
                {RELATIONSHIP_LABELS[member.relationship]}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-xs text-muted-foreground">
                Age {age} · {genderLabel}
              </span>
            </div>
          </div>
        </div>

        {/* Row 2: Medical history */}
        {member.medical_history_summary ? (
          <p className="text-xs text-muted-foreground line-clamp-1 mt-2.5 pl-[60px]">
            {member.medical_history_summary}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground/40 italic mt-2.5 pl-[60px]">
            No medical history
          </p>
        )}

        {/* Row 3: Stats strip */}
        <div className="flex flex-wrap items-center gap-1.5 mt-3">
          {member.blood_group && (
            <span className="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-0.5 text-[11px] font-semibold text-red-600 dark:text-red-400">
              <Droplets className="h-3 w-3" />
              {member.blood_group}
            </span>
          )}
          {member.bmi && (
            <span
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold ${bmiColor || "bg-muted text-muted-foreground"}`}
            >
              <Activity className="h-3 w-3" />
              BMI {member.bmi.toFixed(1)}
            </span>
          )}
          {medCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-0.5 text-[11px] font-semibold text-blue-600 dark:text-blue-400">
              <Pill className="h-3 w-3" />
              {medCount} med{medCount !== 1 ? "s" : ""}
            </span>
          )}
          {condCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 px-2 py-0.5 text-[11px] font-semibold text-rose-600 dark:text-rose-400">
              <Heart className="h-3 w-3" />
              {condCount} condition{condCount !== 1 ? "s" : ""}
            </span>
          )}
          {allergyCount > 0 && (
            <span
              className={`inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold ${allergyColor || "text-amber-600"}`}
            >
              <AlertTriangle className="h-3 w-3" />
              {allergyCount} allerg{allergyCount === 1 ? "y" : "ies"}
            </span>
          )}
        </div>

        {/* Row 4: Quick actions */}
        <div className="flex items-center gap-0.5 mt-3 pt-2.5 border-t border-border/50">
          <TooltipActionLink
            to={`/people/${member.id}/records/new`}
            icon={<FileText className="h-3.5 w-3.5" />}
            label="Add Record"
          />
          <TooltipActionLink
            to={`/people/${member.id}?tab=records`}
            icon={<Calendar className="h-3.5 w-3.5" />}
            label="Timeline"
          />
          <TooltipActionLink
            to={`/people/${member.id}/edit`}
            icon={<Pencil className="h-3.5 w-3.5" />}
            label="Edit"
          />
          <Tooltip>
            <TooltipTrigger>
              <span
                role="button"
                tabIndex={0}
                onClick={() => onDelete(member.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onDelete(member.id);
                }}
                className="ml-auto inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-all duration-200 cursor-pointer"
                aria-label={`Delete ${fullName}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent>Delete</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </Card>
  );
});

/* ── List row ── */

interface MemberRowProps {
  member: FamilyMemberResponse;
  scoreData?: ScoreData;
  onDelete: (id: string) => void;
}

export const MemberRow = memo(function MemberRow({ member, scoreData, onDelete }: MemberRowProps) {
  const color = getRelColor(member.relationship);
  const fullName = `${member.first_name} ${member.last_name}`;
  const initials = getInitials(member.first_name, member.last_name);
  const age = computeAge(member.date_of_birth);
  const genderLabel = GENDER_LABELS[member.gender] || member.gender;
  const allergyCount = member.allergies?.length || 0;
  const medCount = scoreData?.medications ?? 0;

  return (
    <div className="group flex items-center gap-3 rounded-xl border bg-card px-4 py-3 hover:shadow-md hover:border-border transition-all duration-200 select-none">
      {/* Left accent dot */}
      <div
        className={`h-8 w-1 rounded-full bg-gradient-to-b ${color.gradient} opacity-60 group-hover:opacity-100 transition-opacity`}
      />

      {/* Health score / avatar */}
      <Link to={`/people/${member.id}`} className="shrink-0">
        {scoreData !== undefined ? (
          <HealthScoreRing score={scoreData.score} initials={initials} size={40} />
        ) : (
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br ${color.gradient} shadow-sm`}
          >
            <span className="text-xs font-bold text-white">{initials}</span>
          </div>
        )}
      </Link>

      {/* Name + details */}
      <div className="flex-1 min-w-0">
        <Link
          to={`/people/${member.id}`}
          className="text-sm font-semibold text-foreground hover:text-(--brand-primary) transition-colors truncate block"
        >
          {fullName}
        </Link>
      </div>

      {/* Stats row */}
      <div className="hidden sm:flex items-center gap-3 shrink-0">
        <span className="text-xs text-muted-foreground">
          Age {age} · {genderLabel}
        </span>

        <span
          className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${color.text} ${color.bg}`}
        >
          {RELATIONSHIP_LABELS[member.relationship]}
        </span>

        {scoreData !== undefined && scoreData.score > 0 && (
          <span className={`text-xs font-bold ${scoreTextColor(scoreData.score)}`}>
            {scoreData.score}
          </span>
        )}

        {member.blood_group && (
          <span className="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 dark:text-red-400">
            <Droplets className="h-2.5 w-2.5" />
            {member.blood_group}
          </span>
        )}

        {member.bmi && (
          <span className="text-[11px] text-muted-foreground font-medium">
            BMI {member.bmi.toFixed(1)}
          </span>
        )}

        {medCount > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[11px] font-medium text-blue-600 dark:text-blue-400">
            <Pill className="h-3 w-3" />
            {medCount}
          </span>
        )}

        {allergyCount > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[11px] font-medium text-amber-600">
            <AlertTriangle className="h-3 w-3" />
            {allergyCount}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="hidden md:flex items-center gap-0.5 shrink-0">
        <TooltipActionLink
          to={`/people/${member.id}/records/new`}
          icon={<FileText className="h-3.5 w-3.5" />}
          label="Add Record"
          compact
        />
        <TooltipActionLink
          to={`/people/${member.id}/timeline`}
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="Timeline"
          compact
        />
        <TooltipActionLink
          to={`/people/${member.id}/edit`}
          icon={<Pencil className="h-3.5 w-3.5" />}
          label="Edit"
          compact
        />
        <Tooltip>
          <TooltipTrigger>
            <span
              role="button"
              tabIndex={0}
              onClick={() => onDelete(member.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onDelete(member.id);
              }}
              className="inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-all duration-200 cursor-pointer"
              aria-label={`Delete ${fullName}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </span>
          </TooltipTrigger>
          <TooltipContent>Delete</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
});
