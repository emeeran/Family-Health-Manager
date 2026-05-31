import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Users,
  Stethoscope,
  MessageSquare,
  Home,
  CalendarClock,
  Bell,
  Settings,
  FileText,
  Plus,
  ClipboardList,
  Heart,
  FlaskConical,
  Activity,
} from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { listMembers } from "@/lib/api/members";
import { listProviders } from "@/lib/api/providers";
import { listConversations } from "@/lib/api/conversations";
import { listHouseholdRecords, searchHouseholdRecords } from "@/lib/api/household";
import { smartSearchRecords } from "@/lib/api/records";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { useRecordQuickView } from "@/components/records/record-quick-view-provider";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ConversationResponse } from "@/lib/types/conversation";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";

interface SearchResult {
  type: "member" | "provider" | "conversation" | "navigation" | "action" | "record";
  id: string;
  label: string;
  sublabel?: string;
  href: string;
  icon: React.ReactNode;
}

interface GlobalSearchProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const NAV_ITEMS: SearchResult[] = [
  {
    type: "navigation",
    id: "nav-dashboard",
    label: "Go to Dashboard",
    href: "/dashboard",
    icon: <Home className="h-4 w-4 text-blue-500" />,
  },
  {
    type: "navigation",
    id: "nav-members",
    label: "Go to Family Members",
    href: "/members",
    icon: <Users className="h-4 w-4 text-blue-500" />,
  },
  {
    type: "navigation",
    id: "nav-records",
    label: "Go to All Records",
    href: "/records",
    icon: <ClipboardList className="h-4 w-4 text-teal-500" />,
  },
  {
    type: "navigation",
    id: "nav-providers",
    label: "Go to Providers",
    href: "/providers",
    icon: <Stethoscope className="h-4 w-4 text-emerald-500" />,
  },
  {
    type: "navigation",
    id: "nav-reminders",
    label: "Go to Reminders",
    href: "/reminders",
    icon: <CalendarClock className="h-4 w-4 text-amber-500" />,
  },
  {
    type: "navigation",
    id: "nav-notifications",
    label: "Go to Notifications",
    href: "/notifications",
    icon: <Bell className="h-4 w-4 text-amber-500" />,
  },
  {
    type: "navigation",
    id: "nav-settings",
    label: "Go to Settings",
    href: "/settings",
    icon: <Settings className="h-4 w-4 text-slate-500" />,
  },
  {
    type: "action",
    id: "act-member",
    label: "Add Family Member",
    href: "/members/new",
    icon: <Plus className="h-4 w-4 text-blue-500" />,
  },
  {
    type: "action",
    id: "act-provider",
    label: "Add Provider",
    href: "/providers/new",
    icon: <Plus className="h-4 w-4 text-emerald-500" />,
  },
  {
    type: "action",
    id: "act-reminder",
    label: "Create Reminder",
    href: "/reminders/new",
    icon: <Plus className="h-4 w-4 text-amber-500" />,
  },
];

export function GlobalSearch({ open, onOpenChange }: GlobalSearchProps) {
  const navigate = useNavigate();
  const { openQuickView } = useRecordQuickView();
  const [query, setQuery] = useState("");
  const [members, setMembers] = useState<FamilyMemberResponse[]>([]);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [records, setRecords] = useState<HealthRecordResponse[]>([]);
  const [searchResults, setSearchResults] = useState<HealthRecordResponse[]>([]);
  const [aiPowered, setAiPowered] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  // Build member name lookup
  const memberNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const m of members) map[m.id] = `${m.first_name} ${m.last_name}`;
    return map;
  }, [members]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(0);
      return;
    }
    async function loadData() {
      setLoading(true);
      const [m, p, c, r] = await Promise.all([
        listMembers().catch(() => []),
        listProviders().catch(() => []),
        listConversations().catch(() => []),
        listHouseholdRecords(30).catch(() => []),
      ]);
      setMembers(m);
      setProviders(p);
      setConversations(c);
      setRecords(r);
      setLoading(false);
    }
    loadData();
  }, [open]);

  // Debounced server-side record search — uses smart search for complex queries
  useEffect(() => {
    if (!query.trim() || !open) {
      setSearchResults([]);
      setAiPowered(false);
      return;
    }
    const timer = setTimeout(async () => {
      const words = query.trim().split(/\s+/);
      const isComplex =
        words.length > 3 ||
        ["last", "recent", "latest", "this", "all", "'s"].some((kw) =>
          query.toLowerCase().includes(kw)
        );

      if (isComplex) {
        try {
          const smart = await smartSearchRecords(query);
          setAiPowered(smart.ai_powered);
          // Convert smart results to HealthRecordResponse-like format for display
          const converted: HealthRecordResponse[] = smart.results.map((r) => ({
            id: r.id,
            family_member_id: "",
            record_type: r.record_type as RecordType,
            record_date: r.record_date,
            record_time: null,
            clinical_data: r.preview || "",
            diagnosis: r.diagnosis,
            prescription_text: null,
            next_review_date: null,
            provider_id: null,
            provider_name: null,
            is_deleted: false,
            created_at: r.record_date,
            updated_at: r.record_date,
            tags: null,
          }));
          // Patch member names into sublabel via memberNames
          setSearchResults(converted);
          return;
        } catch {
          // Fall through to ILIKE
        }
      }

      setAiPowered(false);
      const results = await searchHouseholdRecords(query, 12).catch(() => []);
      setSearchResults(results);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, open]);

  // Pre-build record icon lookup
  const recordIcons: Record<string, React.ReactNode> = useMemo(
    () => ({
      doctor_visit: <Stethoscope className="h-4 w-4 text-teal-500" />,
      lab_report: <FlaskConical className="h-4 w-4 text-emerald-500" />,
      blood_glucose: <Heart className="h-4 w-4 text-rose-500" />,
      vitals: <Activity className="h-4 w-4 text-blue-500" />,
    }),
    []
  );

  // Pre-build recent records (sorted by created_at, limited to 5)
  const recentRecords = useMemo<SearchResult[]>(() => {
    const sorted = [...records]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 5);
    return sorted.map((r) => {
      const typeLabel = RECORD_TYPE_LABELS[r.record_type] || r.record_type;
      const memberName = r.family_member_id ? memberNames[r.family_member_id] : null;
      return {
        type: "record" as const,
        id: r.id,
        label: r.diagnosis || typeLabel,
        sublabel: `${memberName ? memberName + " — " : ""}${typeLabel} · ${r.record_date}`,
        href: `/members/${r.family_member_id}/records/${r.id}`,
        icon: recordIcons[r.record_type] || <FileText className="h-4 w-4 text-slate-500" />,
      };
    });
  }, [records, memberNames, recordIcons]);

  const results = useMemo<SearchResult[]>(() => {
    const out: SearchResult[] = [];

    if (!query.trim()) {
      // Show recent records + navigation + actions when no query
      return [...recentRecords, ...NAV_ITEMS];
    }

    const q = query.toLowerCase();

    // Navigation + action matches
    for (const item of NAV_ITEMS) {
      if (item.label.toLowerCase().includes(q)) {
        out.push(item);
      }
    }

    // Member matches
    for (const m of members) {
      const name = `${m.first_name} ${m.last_name}`;
      if (name.toLowerCase().includes(q)) {
        out.push({
          type: "member",
          id: m.id,
          label: name,
          sublabel: "Family member",
          href: `/members/${m.id}`,
          icon: <Users className="h-4 w-4 text-blue-500" />,
        });
      }
    }

    // "Add Record" actions when query matches add/new/record
    if (["add", "new", "record"].some((kw) => q.includes(kw))) {
      for (const m of members) {
        const name = `${m.first_name} ${m.last_name}`;
        out.push({
          type: "action",
          id: `add-record-${m.id}`,
          label: `Add Record for ${name}`,
          sublabel: m.relationship || undefined,
          href: `/members/${m.id}/records/new`,
          icon: <Plus className="h-4 w-4 text-teal-500" />,
        });
      }
    }

    // Provider matches
    for (const p of providers) {
      if (p.name.toLowerCase().includes(q) || p.speciality?.toLowerCase().includes(q)) {
        out.push({
          type: "provider",
          id: p.id,
          label: p.name,
          sublabel: p.speciality || "Provider",
          href: `/providers/${p.id}`,
          icon: <Stethoscope className="h-4 w-4 text-emerald-500" />,
        });
      }
    }

    // Conversation matches
    for (const c of conversations) {
      if (c.title?.toLowerCase().includes(q)) {
        out.push({
          type: "conversation",
          id: c.id,
          label: c.title || "Untitled conversation",
          sublabel: "Conversation",
          href: `/conversations/${c.id}`,
          icon: <MessageSquare className="h-4 w-4 text-violet-500" />,
        });
      }
    }

    // Health record matches — use server-side search results
    for (const r of searchResults) {
      const typeLabel = RECORD_TYPE_LABELS[r.record_type] || r.record_type;
      const memberName = r.family_member_id ? memberNames[r.family_member_id] : null;
      out.push({
        type: "record",
        id: r.id,
        label: r.diagnosis || typeLabel,
        sublabel: `${memberName ? memberName + " — " : ""}${typeLabel} · ${r.record_date}`,
        href: `/members/${r.family_member_id}/records/${r.id}`,
        icon: recordIcons[r.record_type] || <FileText className="h-4 w-4 text-slate-500" />,
      });
    }

    return out.slice(0, 12);
  }, [
    query,
    members,
    providers,
    conversations,
    searchResults,
    memberNames,
    recentRecords,
    recordIcons,
  ]);

  // Reset active index when results change
  useEffect(() => {
    setActiveIndex(0);
  }, [results]);

  const handleSelect = useCallback(
    (result: SearchResult) => {
      onOpenChange(false);
      if (result.type === "record" && result.id && result.href) {
        // Extract memberId from href pattern: /members/{memberId}/records/{recordId}
        const match = result.href.match(/\/members\/([^/]+)\/records\/([^/]+)/);
        if (match) {
          openQuickView(match[2], match[1]);
          return;
        }
      }
      navigate(result.href);
    },
    [onOpenChange, navigate, openQuickView]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        onOpenChange(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && results[activeIndex]) {
        e.preventDefault();
        handleSelect(results[activeIndex]);
      }
    },
    [onOpenChange, results, activeIndex, handleSelect]
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg p-0 gap-0 overflow-hidden" showCloseButton={false}>
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription className="sr-only">
          Search and navigate across your health data
        </DialogDescription>
        <div className="flex items-center border-b px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
          <Input
            placeholder="Search or navigate..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex h-11 w-full rounded-none border-0 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
            autoFocus
          />
          {aiPowered && query.trim() && (
            <span className="shrink-0 text-[10px] font-medium text-violet-600 bg-violet-100 dark:bg-violet-500/20 px-1.5 py-0.5 rounded">
              AI
            </span>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto p-2">
          {loading && query.trim() ? (
            <div className="py-6 text-center text-sm text-muted-foreground">Loading...</div>
          ) : results.length === 0 && query.trim() ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              No results found for &ldquo;{query}&rdquo;
            </div>
          ) : (
            <div className="space-y-0.5">
              {!query.trim() && recentRecords.length > 0 && (
                <p className="px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Recent Records
                </p>
              )}
              {results.map((result, i) => {
                // Insert a divider between recent records and nav items when no query
                const showDivider =
                  !query.trim() && i === recentRecords.length && recentRecords.length > 0;
                return (
                  <React.Fragment key={`${result.type}-${result.id}`}>
                    {showDivider && (
                      <div className="flex items-center gap-2 px-3 py-1.5">
                        <div className="h-px flex-1 bg-border" />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                          Navigate
                        </span>
                        <div className="h-px flex-1 bg-border" />
                      </div>
                    )}
                    <button
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors text-left ${
                        i === activeIndex ? "bg-muted/70" : "hover:bg-muted/50"
                      }`}
                      onClick={() => handleSelect(result)}
                      onMouseEnter={() => setActiveIndex(i)}
                    >
                      {result.icon}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{result.label}</p>
                        {result.sublabel && (
                          <p className="text-xs text-muted-foreground">{result.sublabel}</p>
                        )}
                      </div>
                      {result.type === "action" && (
                        <span className="text-[10px] text-muted-foreground bg-muted rounded px-1.5 py-0.5">
                          action
                        </span>
                      )}
                    </button>
                  </React.Fragment>
                );
              })}
            </div>
          )}
        </div>
        <div className="border-t px-3 py-2">
          <p className="text-xs text-muted-foreground flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-0.5 rounded border bg-muted px-1 font-mono text-[10px] font-medium text-muted-foreground">
                ↑↓
              </kbd>
              navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-0.5 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
                ↵
              </kbd>
              open
            </span>
            <span className="flex items-center gap-1">
              <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
                ESC
              </kbd>
              close
            </span>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
