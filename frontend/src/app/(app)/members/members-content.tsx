import { useState, useMemo, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Users,
  Plus,
  Search,
  LayoutGrid,
  List,
  FileText,
  Brain,
  Calendar,
  Pencil,
  Trash2,
  Droplets,
  Activity,
  AlertTriangle,
  ArrowUpDown,
  Heart,
  Pill,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { RELATIONSHIP_LABELS, GENDER_LABELS, BMI_CATEGORY_COLORS } from "@/lib/constants";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { deleteMember, getBatchScores } from "@/lib/api/members";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
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

/* ── Helpers ── */

function computeAge(dob: string): number {
  const today = new Date();
  const birth = new Date(dob);
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return age;
}

function getInitials(first: string, last: string): string {
  return (first[0] + last[0]).toUpperCase();
}

function allergySeverityColor(allergies: FamilyMemberResponse["allergies"]): string | null {
  if (!allergies || allergies.length === 0) return null;
  if (allergies.some((a) => a.severity === "severe")) return "text-red-500";
  if (allergies.some((a) => a.severity === "moderate")) return "text-amber-500";
  return "text-emerald-500";
}

/* ── Score color helpers ── */

function scoreColor(score: number): string {
  if (score >= 75) return "#16a34a";
  if (score >= 50) return "#d97706";
  return "#dc2626";
}

function scoreTextColor(score: number): string {
  if (score >= 75) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

/* ── Relationship filter groups ── */

const FILTER_GROUPS = [
  { key: "all", label: "All" },
  { key: "self", label: "Self" },
  { key: "spouse", label: "Spouse", matches: ["wife"] },
  {
    key: "children",
    label: "Children",
    matches: ["son", "daughter", "grand_son", "grand_daughter"],
  },
  {
    key: "extended",
    label: "Extended",
    matches: ["parent", "daughter_in_law", "son_in_law", "sibling", "others"],
  },
];

/* ── Sort options ── */

const SORT_OPTIONS = [
  { key: "name-asc", label: "Name (A-Z)" },
  { key: "name-desc", label: "Name (Z-A)" },
  { key: "score-desc", label: "Health Score (Best)" },
  { key: "score-asc", label: "Health Score (Lowest)" },
  { key: "age-asc", label: "Age (Youngest)" },
  { key: "age-desc", label: "Age (Oldest)" },
  { key: "recent", label: "Recently Added" },
];

/* ── Storage keys ── */
const VIEW_KEY = "members-view";
const SORT_KEY = "members-sort";

/* ── Score data type ── */
interface ScoreData {
  score: number;
  medications: number;
  conditions: number;
}

/* ── Health Score Ring ── */

function HealthScoreRing({
  score,
  initials,
  size = 48,
}: {
  score: number;
  initials?: string;
  size?: number;
}) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = scoreColor(score);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="shrink-0">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          className="text-muted/30"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {initials ? (
          <span className="text-[10px] font-bold text-foreground/70">{initials}</span>
        ) : (
          <span className="text-sm font-bold" style={{ color }}>
            {score}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Family Summary Bar ── */

function FamilySummaryBar({
  activeCount,
  scores,
  members,
  loading,
}: {
  activeCount: number;
  scores: Record<string, ScoreData>;
  members: FamilyMemberResponse[];
  loading: boolean;
}) {
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
          className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3"
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
}

/* ── Skeleton Grid ── */

function _SkeletonGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i} className="p-4 space-y-3">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 rounded-xl" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-14 rounded-md" />
            <Skeleton className="h-5 w-16 rounded-md" />
          </div>
          <Skeleton className="h-3 w-full" />
          <div className="flex gap-1 pt-2 border-t border-border/50">
            <Skeleton className="h-7 w-7 rounded-lg" />
            <Skeleton className="h-7 w-7 rounded-lg" />
            <Skeleton className="h-7 w-7 rounded-lg" />
            <Skeleton className="h-7 w-7 rounded-lg" />
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ── Main component ── */

interface MembersContentProps {
  members: FamilyMemberResponse[];
}

export function MembersContent({ members }: MembersContentProps) {
  const _navigate = useNavigate();
  const { mutate } = useSWRConfig();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [search, setSearch] = useState("");
  const [filterKey, setFilterKey] = useState("all");
  const [view, setView] = useState<"grid" | "list">(() => {
    if (typeof window === "undefined") return "grid";
    return (localStorage.getItem(VIEW_KEY) as "grid" | "list") || "grid";
  });
  const [sortKey, setSortKey] = useState<string>(() => {
    if (typeof window === "undefined") return "name-asc";
    return localStorage.getItem(SORT_KEY) || "name-asc";
  });

  const [healthScores, setHealthScores] = useState<Record<string, ScoreData>>({});
  const [scoresLoading, setScoresLoading] = useState(true);

  function toggleView(v: "grid" | "list") {
    setView(v);
    localStorage.setItem(VIEW_KEY, v);
  }

  function handleSortChange(value: string | null) {
    if (value) {
      setSortKey(value);
      localStorage.setItem(SORT_KEY, value);
    }
  }

  const activeMembers = useMemo(() => members.filter((m) => m.is_active), [members]);

  /* ── Fetch health scores via single batch call ── */
  useEffect(() => {
    if (!activeMembers.length) {
      setScoresLoading(false);
      return;
    }
    setScoresLoading(true);
    getBatchScores()
      .then((result) => {
        const map: Record<string, ScoreData> = {};
        for (const m of result.members) {
          map[m.member_id] = {
            score: 0,
            medications: m.active_medications_count,
            conditions: 0,
          };
        }
        setHealthScores(map);
      })
      .catch(() => {
        setHealthScores({});
      })
      .finally(() => {
        setScoresLoading(false);
      });
  }, [activeMembers]);

  const filtered = useMemo(() => {
    let result = activeMembers;

    // Search filter
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (m) =>
          m.first_name.toLowerCase().includes(q) ||
          m.last_name.toLowerCase().includes(q) ||
          `${m.first_name} ${m.last_name}`.toLowerCase().includes(q)
      );
    }

    // Relationship filter
    if (filterKey !== "all") {
      const group = FILTER_GROUPS.find((g) => g.key === filterKey);
      if (group?.matches) {
        result = result.filter((m) => group.matches!.includes(m.relationship));
      } else if (group) {
        result = result.filter((m) => m.relationship === filterKey);
      }
    }

    return result;
  }, [activeMembers, search, filterKey]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    switch (sortKey) {
      case "name-asc":
        return arr.sort((a, b) =>
          `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`)
        );
      case "name-desc":
        return arr.sort((a, b) =>
          `${b.first_name} ${b.last_name}`.localeCompare(`${a.first_name} ${a.last_name}`)
        );
      case "score-desc":
        return arr.sort(
          (a, b) => (healthScores[b.id]?.score ?? 0) - (healthScores[a.id]?.score ?? 0)
        );
      case "score-asc":
        return arr.sort(
          (a, b) => (healthScores[a.id]?.score ?? 0) - (healthScores[b.id]?.score ?? 0)
        );
      case "age-asc":
        return arr.sort((a, b) => computeAge(a.date_of_birth) - computeAge(b.date_of_birth));
      case "age-desc":
        return arr.sort((a, b) => computeAge(b.date_of_birth) - computeAge(a.date_of_birth));
      case "recent":
        return arr.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
      default:
        return arr;
    }
  }, [filtered, sortKey, healthScores]);

  async function handleDelete() {
    try {
      await deleteMember(deleteId);
      toast.success("Member deleted");
      setDeleteOpen(false);
      mutate(() => true, undefined, { revalidate: true });
    } catch {
      toast.error("Failed to delete member");
    }
  }

  /* ── Empty state ── */
  if (members.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader count={0} />
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-(--brand-accent)/15 to-(--brand-primary)/15">
              <Users className="h-8 w-8 text-(--brand-accent)" />
            </div>
          }
          title="No family members yet"
          description="Add your first family member to start tracking their health records."
          action={
            <Link
              to="/members/new"
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-(--brand-accent) to-(--brand-primary) px-4 h-9 text-sm font-semibold text-white hover:opacity-90 transition-opacity shadow-md"
            >
              <Plus className="h-4 w-4" />
              Add your first member
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="space-y-5">
        <PageHeader count={activeMembers.length} total={members.length} />

        {/* ── Summary bar ── */}
        <FamilySummaryBar
          activeCount={activeMembers.length}
          scores={healthScores}
          members={activeMembers}
          loading={scoresLoading}
        />

        {/* ── Toolbar ── */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 w-full sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search members..."
              className="w-full h-9 rounded-lg border border-border/60 bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-(--brand-primary)/20 focus:border-(--brand-primary)/30 transition-all"
            />
          </div>

          {/* Relationship filter pills */}
          <div className="flex items-center gap-1 flex-wrap">
            {FILTER_GROUPS.map((g) => (
              <button
                key={g.key}
                onClick={() => setFilterKey(g.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  filterKey === g.key
                    ? "bg-(--brand-primary)/10 text-(--brand-primary) dark:text-(--brand-accent) shadow-sm"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>

          {/* Sort + View toggle + Add */}
          <div className="flex items-center gap-2 ml-auto">
            <Select value={sortKey} onValueChange={handleSortChange}>
              <SelectTrigger size="sm" className="h-9 gap-1.5 text-xs">
                <ArrowUpDown className="h-3.5 w-3.5" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((opt) => (
                  <SelectItem key={opt.key} value={opt.key}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="flex items-center rounded-lg border border-border/60 overflow-hidden">
              <button
                onClick={() => toggleView("grid")}
                className={`p-2 transition-colors ${view === "grid" ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                aria-label="Grid view"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => toggleView("list")}
                className={`p-2 transition-colors ${view === "list" ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                aria-label="List view"
              >
                <List className="h-4 w-4" />
              </button>
            </div>
            <Link
              to="/members/new"
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-(--brand-accent) to-(--brand-primary) px-3.5 h-9 text-sm font-semibold text-white hover:opacity-90 transition-opacity shadow-md"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Add Member</span>
            </Link>
          </div>
        </div>

        {/* ── Members display ── */}
        {filtered.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-sm text-muted-foreground">No members match your search.</p>
          </div>
        ) : view === "grid" ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sorted.map((member) => (
              <MemberCard
                key={member.id}
                member={member}
                scoreData={healthScores[member.id]}
                onDelete={(id) => {
                  setDeleteId(id);
                  setDeleteOpen(true);
                }}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {sorted.map((member) => (
              <MemberRow
                key={member.id}
                member={member}
                scoreData={healthScores[member.id]}
                onDelete={(id) => {
                  setDeleteId(id);
                  setDeleteOpen(true);
                }}
              />
            ))}
          </div>
        )}

        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          title="Delete Member"
          description="Are you sure you want to delete this member? All their health records will also be deleted."
          onConfirm={handleDelete}
        />
      </div>
    </TooltipProvider>
  );
}

/* ── Page header ── */

function PageHeader({ count, total }: { count: number; total?: number }) {
  return (
    <div className="flex items-end justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Family Members</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {count} active member{count !== 1 ? "s" : ""}
          {total !== undefined && total !== count && ` · ${total - count} inactive`}
        </p>
      </div>
    </div>
  );
}

/* ── Grid card ── */

function MemberCard({
  member,
  scoreData,
  onDelete,
}: {
  member: FamilyMemberResponse;
  scoreData?: ScoreData;
  onDelete: (id: string) => void;
}) {
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

  return (
    <Card className="group relative overflow-hidden hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200">
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
                to={`/members/${member.id}`}
                className="text-base font-bold text-foreground hover:text-(--brand-primary) transition-colors truncate"
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
            to={`/members/${member.id}/records/new`}
            icon={<FileText className="h-3.5 w-3.5" />}
            label="Add Record"
          />
          <TooltipActionLink
            to={`/members/${member.id}/ai`}
            icon={<Brain className="h-3.5 w-3.5" />}
            label="AI Chat"
          />
          <TooltipActionLink
            to={`/members/${member.id}/timeline`}
            icon={<Calendar className="h-3.5 w-3.5" />}
            label="Timeline"
          />
          <TooltipActionLink
            to={`/members/${member.id}/edit`}
            icon={<Pencil className="h-3.5 w-3.5" />}
            label="Edit"
          />
          <Tooltip>
            <TooltipTrigger>
              <button
                onClick={() => onDelete(member.id)}
                className="ml-auto inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-all duration-200"
                aria-label={`Delete ${fullName}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Delete</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </Card>
  );
}

/* ── List row ── */

function MemberRow({
  member,
  scoreData,
  onDelete,
}: {
  member: FamilyMemberResponse;
  scoreData?: ScoreData;
  onDelete: (id: string) => void;
}) {
  const color = getRelColor(member.relationship);
  const fullName = `${member.first_name} ${member.last_name}`;
  const initials = getInitials(member.first_name, member.last_name);
  const age = computeAge(member.date_of_birth);
  const genderLabel = GENDER_LABELS[member.gender] || member.gender;
  const allergyCount = member.allergies?.length || 0;
  const medCount = scoreData?.medications ?? 0;

  return (
    <div className="group flex items-center gap-3 rounded-xl border bg-card px-4 py-3 hover:shadow-md hover:border-border transition-all duration-200">
      {/* Left accent dot */}
      <div
        className={`h-8 w-1 rounded-full bg-gradient-to-b ${color.gradient} opacity-60 group-hover:opacity-100 transition-opacity`}
      />

      {/* Health score / avatar */}
      <Link to={`/members/${member.id}`} className="shrink-0">
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
          to={`/members/${member.id}`}
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
          to={`/members/${member.id}/records/new`}
          icon={<FileText className="h-3.5 w-3.5" />}
          label="Add Record"
          compact
        />
        <TooltipActionLink
          to={`/members/${member.id}/ai`}
          icon={<Brain className="h-3.5 w-3.5" />}
          label="AI Chat"
          compact
        />
        <TooltipActionLink
          to={`/members/${member.id}/timeline`}
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="Timeline"
          compact
        />
        <TooltipActionLink
          to={`/members/${member.id}/edit`}
          icon={<Pencil className="h-3.5 w-3.5" />}
          label="Edit"
          compact
        />
        <Tooltip>
          {/* @ts-expect-error Radix TooltipTrigger supports asChild */}
          <TooltipTrigger asChild>
            <button
              onClick={() => onDelete(member.id)}
              className="inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-all duration-200"
              aria-label={`Delete ${fullName}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent>Delete</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

/* ── Tooltip action link ── */

function TooltipActionLink({
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
}
