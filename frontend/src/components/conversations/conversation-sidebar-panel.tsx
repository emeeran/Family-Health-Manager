import { useState, useMemo } from "react";
import { Plus, Trash2, MessageSquare, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { deleteConversation } from "@/lib/api/conversations";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import type { ConversationResponse } from "@/lib/types/conversation";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { cn, formatRelativeTime } from "@/lib/utils";

type ScopeFilter = "all" | "general" | "member";

interface ConversationSidebarPanelProps {
  conversations: ConversationResponse[];
  members: FamilyMemberResponse[];
  activeConvId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onActiveDeleted?: () => void;
}

export function ConversationSidebarPanel({
  conversations,
  members,
  activeConvId,
  onSelectConversation,
  onNewChat,
  onActiveDeleted,
}: ConversationSidebarPanelProps) {
  const { mutate } = useSWRConfig();
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");

  const memberMap = useMemo(
    () => new Map(members.map((m) => [m.id, `${m.first_name} ${m.last_name}`])),
    [members]
  );

  const filteredConversations = useMemo(() => {
    return [...conversations]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .filter((conv) => {
        if (scopeFilter === "general" && conv.scope !== "general") return false;
        if (scopeFilter === "member" && conv.scope !== "member") return false;
        return true;
      });
  }, [conversations, scopeFilter]);

  async function handleDelete() {
    try {
      const wasActive = deleteId === activeConvId;
      await deleteConversation(deleteId);
      toast.success("Deleted");
      setDeleteOpen(false);
      await mutate("conversations-page");
      if (wasActive && onActiveDeleted) {
        onActiveDeleted();
      }
    } catch {
      toast.error("Failed to delete");
    }
  }

  const filters: { value: ScopeFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "general", label: "General" },
    { value: "member", label: "Members" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* New chat + filter */}
      <div className="px-3 pt-3 pb-2 shrink-0 space-y-2">
        <Button
          variant="outline"
          onClick={onNewChat}
          className="w-full justify-start gap-2 h-9 text-sm font-medium rounded-lg"
        >
          <Plus className="h-4 w-4" />
          New chat
        </Button>
        <div className="flex gap-1">
          {filters.map((f) => (
            <button
              key={f.value}
              onClick={() => setScopeFilter(f.value)}
              className={cn(
                "px-2 py-0.5 text-[11px] font-medium rounded-full transition-colors",
                scopeFilter === f.value
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filteredConversations.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-[11px] text-muted-foreground/40">No conversations</p>
          </div>
        ) : (
          <div className="space-y-px">
            {filteredConversations.map((conv) => {
              const memberName = conv.family_member_id
                ? memberMap.get(conv.family_member_id)
                : null;
              const isActive = conv.id === activeConvId;
              const isMember = conv.scope === "member";

              return (
                <div
                  key={conv.id}
                  className={cn(
                    "group flex items-center gap-2 rounded-lg px-2.5 py-2 cursor-pointer transition-colors",
                    isActive ? "bg-muted" : "hover:bg-muted/50"
                  )}
                  onClick={() => onSelectConversation(conv.id)}
                >
                  <div
                    className={cn(
                      "shrink-0",
                      isActive ? "text-foreground/60" : "text-muted-foreground/30"
                    )}
                  >
                    {isMember ? (
                      <User className="h-3.5 w-3.5" />
                    ) : (
                      <MessageSquare className="h-3.5 w-3.5" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        "text-[13px] truncate",
                        isActive ? "font-medium text-foreground" : "text-foreground/75"
                      )}
                    >
                      {conv.title || "Untitled"}
                    </p>
                    <p className="text-[10px] text-muted-foreground/45 truncate">
                      {isMember && memberName ? memberName : "General"} ·{" "}
                      {formatRelativeTime(conv.updated_at)}
                    </p>
                  </div>
                  <button
                    className="touch-compact shrink-0 opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-destructive transition-all"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteId(conv.id);
                      setDeleteOpen(true);
                    }}
                    aria-label="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Conversation"
        description="Are you sure you want to delete this conversation?"
        onConfirm={handleDelete}
      />
    </div>
  );
}
