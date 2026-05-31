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
  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b shrink-0">
      {/* Mobile hamburger */}
      <button
        onClick={onToggleSidebar}
        className="flex md:hidden items-center justify-center h-7 w-7 rounded-md hover:bg-muted transition-colors"
        aria-label="Toggle sidebar"
      >
        <PanelLeft className="h-4 w-4" />
      </button>

      {/* Mode toggle — compact icon + label */}
      <div className="flex items-center rounded-md bg-muted/60 p-0.5">
        <button
          onClick={() => onModeChange("general")}
          className={cn(
            "flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-sm transition-all",
            mode === "general"
              ? "bg-background shadow-xs text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <MessageSquare className="h-3 w-3" />
          General
        </button>
        <button
          onClick={() => onModeChange("member")}
          className={cn(
            "flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-sm transition-all",
            mode === "member"
              ? "bg-background shadow-xs text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <User className="h-3 w-3" />
          Private
        </button>
      </div>

      {/* Member selector — only in member mode */}
      {mode === "member" && (
        <Select value={selectedMemberId ?? ""} onValueChange={(v) => onMemberChange(v || null)}>
          <SelectTrigger className="w-36 h-7 text-xs border-dashed">
            <SelectValue placeholder="Pick member" />
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

      {/* Spacer */}
      <div className="flex-1" />
    </div>
  );
}
