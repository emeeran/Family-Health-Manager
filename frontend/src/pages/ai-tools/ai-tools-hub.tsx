import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { listMembers } from "@/lib/api/members";
import { ViewToggle, useViewPreference } from "@/components/shared/view-toggle";
import type { FamilyMemberResponse } from "@/lib/types/member";
import {
  MessageSquare,
  Brain,
  ClipboardCheck,
  Pill,
  FileText,
  PenLine,
  Users,
  Loader2,
  ChevronRight,
} from "lucide-react";

interface ToolCard {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  path: string;
  color: string;
}

const tools: ToolCard[] = [
  {
    title: "Chat Assistant",
    description: "Ask questions about health records in a conversational interface",
    icon: MessageSquare,
    path: "/ai-tools/chat",
    color: "text-blue-500",
  },
  {
    title: "Health Insights",
    description: "AI-generated health assessments and clinical analysis",
    icon: Brain,
    path: "/ai-tools/insights",
    color: "text-purple-500",
  },
  {
    title: "Pre-consultation Notes",
    description: "Prepare notes and checklists for upcoming doctor visits",
    icon: ClipboardCheck,
    path: "/ai-tools/pre-consultation",
    color: "text-emerald-500",
  },
  {
    title: "Drug Interactions",
    description: "Check current medications for potential interactions",
    icon: Pill,
    path: "/ai-tools/drug-interactions",
    color: "text-red-500",
  },
  {
    title: "Consultation Summaries",
    description: "Generate and manage AI summaries for health records",
    icon: FileText,
    path: "/ai-tools/summaries",
    color: "text-amber-500",
  },
  {
    title: "Smart Entry",
    description: "Create structured records from natural language descriptions",
    icon: PenLine,
    path: "/ai-tools/smart-entry",
    color: "text-cyan-500",
  },
];

export default function AiToolsHubPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [members, setMembers] = useState<FamilyMemberResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useViewPreference("ai-tools-view", "grid");

  const selectedMemberId = searchParams.get("memberId") || "";

  useEffect(() => {
    listMembers()
      .then(setMembers)
      .catch(() => setMembers([]))
      .finally(() => setLoading(false));
  }, []);

  function handleMemberChange(value: string | null) {
    const memberId = value || "__none__";
    if (memberId === "__none__") {
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ memberId }, { replace: true });
    }
  }

  function handleToolClick(path: string) {
    if (!selectedMemberId) return;
    navigate(`${path}?memberId=${selectedMemberId}`);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Tools</h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI-powered health tools for your family members
          </p>
        </div>
        <ViewToggle value={view} onChange={setView} />
      </div>

      {/* Member Selector */}
      <Card>
        <div className="p-4">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Select Family Member
              </Label>
              {loading ? (
                <div className="flex items-center gap-2 mt-1.5">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Loading members...</span>
                </div>
              ) : (
                <Select value={selectedMemberId || "__none__"} onValueChange={handleMemberChange}>
                  <SelectTrigger className="mt-1.5">
                    <SelectValue placeholder="Choose a family member to get started" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Choose a family member...</SelectItem>
                    {members.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.first_name} {m.last_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            {selectedMemberId && (
              <div className="flex items-center gap-1.5 text-sm text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
                <Users className="h-3.5 w-3.5" />
                {members.find((m) => m.id === selectedMemberId)
                  ? `${members.find((m) => m.id === selectedMemberId)!.first_name} ${members.find((m) => m.id === selectedMemberId)!.last_name}`
                  : "Selected"}
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Tools */}
      {view === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((tool) => {
            const Icon = tool.icon;
            const disabled = !selectedMemberId;
            return (
              <Card
                key={tool.path}
                className={`transition-all duration-200 ${
                  disabled
                    ? "opacity-50 cursor-not-allowed"
                    : "cursor-pointer hover:shadow-md hover:border-primary/30 hover:bg-accent/30"
                }`}
                onClick={() => !disabled && handleToolClick(tool.path)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-9 w-9 rounded-lg flex items-center justify-center bg-muted/50 ${tool.color}`}
                    >
                      <Icon className="h-4.5 w-4.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <CardTitle className="text-sm">{tool.title}</CardTitle>
                    </div>
                  </div>
                  <CardDescription className="text-xs mt-1.5 ml-12">
                    {tool.description}
                  </CardDescription>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      ) : (
        /* List view */
        <div className="rounded-lg border bg-card divide-y">
          {tools.map((tool) => {
            const Icon = tool.icon;
            const disabled = !selectedMemberId;
            return (
              <div
                key={tool.path}
                className={`flex items-center gap-4 px-4 py-3 transition-colors ${
                  disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-muted/30"
                }`}
                onClick={() => !disabled && handleToolClick(tool.path)}
              >
                <div
                  className={`h-9 w-9 rounded-lg flex items-center justify-center bg-muted/50 shrink-0 ${tool.color}`}
                >
                  <Icon className="h-4.5 w-4.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{tool.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{tool.description}</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground/40 shrink-0" />
              </div>
            );
          })}
        </div>
      )}

      {/* Help text when no member selected */}
      {!selectedMemberId && !loading && members.length > 0 && (
        <div className="text-center py-8">
          <Users className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
          <p className="text-sm font-medium text-muted-foreground">
            Select a family member above to unlock AI tools
          </p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            All tools are scoped to the selected member's health data
          </p>
        </div>
      )}

      {!loading && members.length === 0 && (
        <div className="text-center py-8">
          <Users className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
          <p className="text-sm font-medium text-muted-foreground">No family members found</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => navigate("/people/new")}
          >
            Add a Family Member
          </Button>
        </div>
      )}
    </div>
  );
}
