import { useState, useMemo, useEffect, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Users, Plus, Search, ArrowUpDown } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TooltipProvider } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { ViewToggle, useViewPreference } from "@/components/shared/view-toggle";
import { deleteMember, getBatchScores } from "@/lib/api/members";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { ErrorState } from "@/components/shared/error-state";
import { computeAge } from "@/lib/utils";
import { FamilySummaryBar } from "@/components/members/family-summary";
import { MemberCard, MemberRow } from "@/components/members/member-card";
import type { FamilyMemberResponse } from "@/lib/types/member";

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

const SORT_OPTIONS = [
  { key: "name-asc", label: "Name (A-Z)" },
  { key: "name-desc", label: "Name (Z-A)" },
  { key: "score-desc", label: "Health Score (Best)" },
  { key: "score-asc", label: "Health Score (Lowest)" },
  { key: "age-asc", label: "Age (Youngest)" },
  { key: "age-desc", label: "Age (Oldest)" },
  { key: "recent", label: "Recently Added" },
];

const VIEW_KEY = "members-view";
const SORT_KEY = "members-sort";

interface ScoreData {
  score: number;
  medications: number;
  conditions: number;
}

interface MembersContentProps {
  members: FamilyMemberResponse[];
}

function PageHeader({ count, total }: { count: number; total?: number }) {
  return (
    <div className="flex items-end justify-between select-none">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Family Members</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {count} active member{count !== 1 ? "s" : ""}
          {total !== undefined && total !== count && ` · ${total - count} inactive`}
        </p>
      </div>
    </div>
  );
}

export function MembersContent({ members }: MembersContentProps) {
  const navigate = useNavigate();
  const { mutate: swrMutate } = useSWRConfig();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [search, setSearch] = useState("");
  const [filterKey, setFilterKey] = useState("all");
  const [view, setView] = useViewPreference(VIEW_KEY, "grid");
  const [sortKey, setSortKey] = useState<string>(() => {
    if (typeof window === "undefined") return "name-asc";
    return localStorage.getItem(SORT_KEY) || "name-asc";
  });

  const [healthScores, setHealthScores] = useState<Record<string, ScoreData>>({});
  const [scoresLoading, setScoresLoading] = useState(true);

  const activeMembers = useMemo(() => (members ?? []).filter((m) => m.is_active), [members]);

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

  const handleRequestDelete = useCallback((id: string) => {
    setDeleteId(id);
    setDeleteOpen(true);
  }, []);

  function handleSortChange(value: string | null) {
    if (value) {
      setSortKey(value);
      localStorage.setItem(SORT_KEY, value);
    }
  }

  const filtered = useMemo(() => {
    let result = activeMembers;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (m) =>
          m.first_name.toLowerCase().includes(q) ||
          m.last_name.toLowerCase().includes(q) ||
          `${m.first_name} ${m.last_name}`.toLowerCase().includes(q)
      );
    }
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
      await Promise.all([swrMutate("members"), swrMutate("dashboard")]);
    } catch {
      toast.error("Failed to delete member");
    }
  }

  if (members.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader count={0} />
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
              <Users className="h-8 w-8 text-primary" />
            </div>
          }
          title="No family members yet"
          description="Add your first family member to start tracking their health records."
          action={
            <Link
              to="/people/new"
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 h-9 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
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
      <div className="space-y-4">
        <PageHeader count={activeMembers.length} total={members.length} />

        <FamilySummaryBar
          activeCount={activeMembers.length}
          scores={healthScores}
          members={activeMembers}
          loading={scoresLoading}
        />

        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="relative flex-1 w-full sm:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search members..."
              className="w-full h-9 rounded-lg border border-border/60 bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/30 transition-all"
            />
          </div>

          <div className="flex items-center gap-1 flex-wrap">
            {FILTER_GROUPS.map((g) => (
              <button
                key={g.key}
                onClick={() => setFilterKey(g.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  filterKey === g.key
                    ? "bg-primary/10 text-primary shadow-sm"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>

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

            <ViewToggle value={view} onChange={setView} />
            <button
              onClick={() => navigate("/people/new")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 h-9 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Add Member</span>
            </button>
          </div>
        </div>

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
                onDelete={handleRequestDelete}
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
                onDelete={handleRequestDelete}
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
