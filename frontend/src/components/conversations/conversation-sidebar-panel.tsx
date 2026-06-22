import { useState, useMemo, useRef, useEffect } from "react";
import { Plus, Trash2, MessageSquare, User, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { deleteConversation, updateConversation } from "@/lib/api/conversations";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import type { ConversationResponse } from "@/lib/types/conversation";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { cn, formatRelativeTime } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type ScopeFilter = "all" | "general" | "member";

interface ConversationSidebarPanelProps {
  conversations: ConversationResponse[];
  members: FamilyMemberResponse[];
  activeConvId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onActiveDeleted?: () => void;
  onRefresh?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function ConversationSidebarPanel({
  conversations,
  members,
  activeConvId,
  onSelectConversation,
  onNewChat,
  onActiveDeleted,
  onRefresh,
  collapsed = false,
  onToggleCollapse,
}: ConversationSidebarPanelProps) {
  const { mutate } = useSWRConfig();
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  const memberMap = useMemo(
    () => new Map(members.map((m) => [m.id, `${m.first_name} ${m.last_name}`])),
    [members]
  );

  async function handleRename(convId: string, newTitle: string) {
    if (!newTitle.trim()) return;
    try {
      await updateConversation(convId, { title: newTitle.trim() });
      onRefresh?.();
    } catch {
      /* ignore rename failure */
    }
    setRenamingId(null);
  }

  const [searchQuery, setSearchQuery] = useState("");

  const filteredConversations = useMemo(() => {
    return [...conversations]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .filter((conv) => {
        if (scopeFilter === "general" && conv.scope !== "general") return false;
        if (scopeFilter === "member" && conv.scope !== "member") return false;
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          return (conv.title || "").toLowerCase().includes(q);
        }
        return true;
      });
  }, [conversations, scopeFilter, searchQuery]);

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

  /* ── Collapsed: icon rail ── */
  if (collapsed) {
    return (
      <div className="flex flex-col h-full overflow-hidden items-center py-2 gap-1">
        <TooltipProvider delay={300}>
          <Tooltip>
            <TooltipTrigger>
              <button
                onClick={onNewChat}
                className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-muted/60 transition-colors"
                aria-label="New chat"
              >
                <Plus className="h-4 w-4 text-muted-foreground" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">New chat</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <div className="w-6 border-t border-border/40 my-1" />

        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden w-full flex flex-col items-center gap-0.5 px-1.5">
          {filteredConversations.map((conv) => {
            const isActive = conv.id === activeConvId;
            const isMember = conv.scope === "member";
            const Icon = isMember ? User : MessageSquare;

            return (
              <TooltipProvider key={conv.id} delay={300}>
                <Tooltip>
                  <TooltipTrigger>
                    <button
                      onClick={() => onSelectConversation(conv.id)}
                      className={cn(
                        "flex items-center justify-center w-9 h-9 rounded-lg transition-colors",
                        isActive
                          ? "bg-muted text-foreground"
                          : "text-muted-foreground/50 hover:bg-muted/40 hover:text-foreground"
                      )}
                      aria-label={conv.title || "Untitled"}
                    >
                      <Icon className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-[200px]">
                    <p className="truncate text-xs font-medium">{conv.title || "Untitled"}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            );
          })}
        </div>

        <div className="w-6 border-t border-border/40 my-1" />

        <TooltipProvider delay={300}>
          <Tooltip>
            <TooltipTrigger>
              <button
                onClick={onToggleCollapse}
                className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-muted/60 transition-colors"
                aria-label="Expand sidebar"
              >
                <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar</TooltipContent>
          </Tooltip>
        </TooltipProvider>

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

  /* ── Expanded: full panel ── */
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header with toggle */}
      <div className="px-3 pt-3 pb-1 shrink-0 flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">Conversations</span>
        <button
          onClick={onToggleCollapse}
          className="flex items-center justify-center h-6 w-6 rounded-md hover:bg-muted/60 transition-colors"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* New chat + filter */}
      <div className="px-3 pb-2 shrink-0 space-y-2">
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
        {conversations.length > 5 && (
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-7 px-2.5 text-xs rounded-md border border-border bg-background placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        )}
      </div>

      {/* Conversation list */}
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-2 pb-2">
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
                  onClick={() => {
                    if (renamingId !== conv.id) onSelectConversation(conv.id);
                  }}
                  onDoubleClick={() => {
                    setRenamingId(conv.id);
                    setRenameValue(conv.title || "");
                  }}
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
                    {renamingId === conv.id ? (
                      <input
                        ref={renameInputRef}
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => handleRename(conv.id, renameValue)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRename(conv.id, renameValue);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full text-[13px] bg-background border border-border rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-ring"
                      />
                    ) : (
                      <p
                        className={cn(
                          "text-[13px] truncate",
                          isActive ? "font-medium text-foreground" : "text-foreground/75"
                        )}
                      >
                        {conv.title || "Untitled"}
                      </p>
                    )}
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
