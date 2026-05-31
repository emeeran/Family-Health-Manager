import { useState, useMemo } from "react";
import { Plus, Trash2, MessageSquare, User, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
}

export function ConversationSidebarPanel({
  conversations,
  members,
  activeConvId,
  onSelectConversation,
  onNewChat,
}: ConversationSidebarPanelProps) {
  const { mutate } = useSWRConfig();
  const [searchText, setSearchText] = useState("");
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");

  const memberMap = useMemo(
    () => new Map(members.map((m) => [m.id, `${m.first_name} ${m.last_name}`])),
    [members]
  );

  const filteredConversations = useMemo(() => {
    return conversations
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .filter((conv) => {
        if (scopeFilter === "general" && conv.scope !== "general") return false;
        if (scopeFilter === "member" && conv.scope !== "member") return false;
        if (searchText.trim()) {
          const q = searchText.toLowerCase();
          const title = (conv.title || "").toLowerCase();
          const memberName = conv.family_member_id
            ? memberMap.get(conv.family_member_id)?.toLowerCase()
            : "";
          return title.includes(q) || (memberName && memberName.includes(q));
        }
        return true;
      });
  }, [conversations, searchText, scopeFilter, memberMap]);

  async function handleDelete() {
    try {
      await deleteConversation(deleteId);
      toast.success("Deleted");
      setDeleteOpen(false);
      mutate("conversations-page");
    } catch {
      toast.error("Failed to delete");
    }
  }

  const tabs: { value: ScopeFilter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "general", label: "General" },
    { value: "member", label: "Members" },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Chats
          </h2>
          <Button variant="ghost" size="icon-sm" onClick={onNewChat} title="New chat">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Search */}
        <div className="relative mb-2">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground/60" />
          <Input
            placeholder="Search..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-7 h-7 text-xs border-dashed"
          />
        </div>

        {/* Scope tabs */}
        <div className="flex gap-0.5 rounded-md bg-muted/50 p-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setScopeFilter(tab.value)}
              className={cn(
                "flex-1 px-2 py-1 text-[11px] font-medium rounded-sm transition-all",
                scopeFilter === tab.value
                  ? "bg-background shadow-xs text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {filteredConversations.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground/60">No conversations</p>
        ) : (
          filteredConversations.map((conv) => {
            const memberName = conv.family_member_id ? memberMap.get(conv.family_member_id) : null;
            const isActive = conv.id === activeConvId;
            const isMember = conv.scope === "member";

            return (
              <div
                key={conv.id}
                className={cn(
                  "group flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer transition-colors",
                  isActive ? "bg-primary/10" : "hover:bg-muted/50"
                )}
                onClick={() => onSelectConversation(conv.id)}
              >
                {/* Scope icon */}
                <div
                  className={cn(
                    "shrink-0 flex h-6 w-6 items-center justify-center rounded",
                    isActive ? "text-primary" : "text-muted-foreground/50"
                  )}
                >
                  {isMember ? <User className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}
                </div>

                {/* Title + subtitle */}
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      "text-xs truncate",
                      isActive ? "font-medium" : "text-foreground/80"
                    )}
                  >
                    {conv.title || "Untitled"}
                  </p>
                  <p className="text-[10px] text-muted-foreground/60 truncate">
                    {isMember && memberName ? memberName : "General"} ·{" "}
                    {formatRelativeTime(conv.updated_at)}
                  </p>
                </div>

                {/* Delete */}
                <button
                  className="shrink-0 opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-destructive transition-all"
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
          })
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
