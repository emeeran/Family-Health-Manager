import { useMemo } from "react";
import { MessageSquare, PanelLeft, User } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { cn } from "@/lib/utils";

interface ChatHeaderProps {
  mode: "general" | "member";
  onModeChange: (mode: "general" | "member") => void;
  selectedMemberId: string | null;
  onMemberChange: (memberId: string | null) => void;
  members: FamilyMemberResponse[];
  onToggleSidebar: () => void;
}

export function ChatHeader({
  mode,
  onModeChange,
  selectedMemberId,
  onMemberChange,
  members,
  onToggleSidebar,
}: ChatHeaderProps) {
  const selectedMemberDisplay = useMemo(() => {
    if (!selectedMemberId) return undefined;
    const m = members.find((member) => member.id === selectedMemberId);
    return m ? `${m.first_name} ${m.last_name}` : "Loading…";
  }, [selectedMemberId, members]);

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b border-border/30">
      {/* Mobile sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        className="touch-compact flex md:hidden items-center justify-center h-8 w-8 rounded-lg hover:bg-muted/60 transition-colors"
        aria-label="Toggle sidebar"
      >
        <PanelLeft className="h-4 w-4" />
      </button>

      {/* Mode toggle — pill style */}
      <div className="flex items-center rounded-full bg-muted/50 p-0.5">
        <button
          onClick={() => onModeChange("general")}
          className={cn(
            "flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-full transition-all",
            mode === "general"
              ? "bg-card shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <MessageSquare className="h-3 w-3" />
          General
        </button>
        <button
          onClick={() => onModeChange("member")}
          className={cn(
            "flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-full transition-all",
            mode === "member"
              ? "bg-card shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <User className="h-3 w-3" />
          Private
        </button>
      </div>

      {/* Member selector */}
      {mode === "member" && (
        <Select value={selectedMemberId ?? ""} onValueChange={(v) => onMemberChange(v || null)}>
          <SelectTrigger className="w-36 h-8 text-xs rounded-full border-dashed">
            <SelectValue placeholder="Pick member">{selectedMemberDisplay}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {members.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.first_name} {m.last_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <div className="flex-1" />
    </div>
  );
}
