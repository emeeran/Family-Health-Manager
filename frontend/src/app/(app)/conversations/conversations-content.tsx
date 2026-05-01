import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { Plus, Trash2, Bot, User, Sparkles, X, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { deleteConversation } from "@/lib/api/conversations";
import { createConversation } from "@/lib/api/conversations";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import type { ConversationResponse } from "@/lib/types/conversation";
import type { FamilyMemberResponse } from "@/lib/types/member";

function relativeTime(date: string | Date): string {
  const now = new Date();
  const d = new Date(date);
  const seconds = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface ConversationsContentProps {
  conversations: ConversationResponse[];
  members: FamilyMemberResponse[];
}

export function ConversationsContent({ conversations, members }: ConversationsContentProps) {
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [chatTitle, setChatTitle] = useState("");
  const [chatMemberId, setChatMemberId] = useState("");
  const [creating, setCreating] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [scopeFilter, setScopeFilter] = useState<"all" | "general" | "member">("all");

  const memberMap = useMemo(
    () => new Map(members.map((m) => [m.id, `${m.first_name} ${m.last_name}`])),
    [members]
  );

  const filteredConversations = useMemo(() => {
    return conversations.filter((conv) => {
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
      toast.success("Conversation deleted");
      setDeleteOpen(false);
      mutate(() => true, undefined, { revalidate: true });
    } catch {
      toast.error("Failed to delete conversation");
    }
  }

  async function handleCreateChat(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const conv = await createConversation({
        scope: chatMemberId ? "member" : "general",
        title: chatTitle.trim() || null,
        family_member_id: chatMemberId || null,
      });
      navigate(`/conversations/${conv.id}`);
    } catch {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Conversations</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {conversations.length} conversation{conversations.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button onClick={() => setNewChatOpen(true)} className="shadow-sm">
          <Plus className="h-4 w-4 mr-1.5" />
          New Chat
        </Button>
      </div>

      {/* New Chat Panel */}
      {newChatOpen && (
        <Card className="border-primary/20 bg-primary/[0.02] animate-fade-in-up">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-violet-500" />
                Start New Conversation
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => setNewChatOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreateChat} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="chat_title">Title (optional)</Label>
                <Input
                  id="chat_title"
                  value={chatTitle}
                  onChange={(e) => setChatTitle(e.target.value)}
                  placeholder="e.g., Questions about blood work"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="chat_member">Family Member (optional)</Label>
                <Select
                  value={chatMemberId}
                  onValueChange={(v) => setChatMemberId(v === "__none__" ? "" : (v ?? ""))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="General chat (no member)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">General chat</SelectItem>
                    {members.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.first_name} {m.last_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={creating}>
                  {creating ? "Creating..." : "Start Chat"}
                </Button>
                <Button type="button" variant="outline" onClick={() => setNewChatOpen(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Search and Filter */}
      {conversations.length > 0 && (
        <div className="flex gap-3 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search conversations..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select
            value={scopeFilter}
            onValueChange={(v) => setScopeFilter(v as "all" | "general" | "member")}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Chats</SelectItem>
              <SelectItem value="general">General</SelectItem>
              <SelectItem value="member">Member-specific</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {conversations.length === 0 && !newChatOpen ? (
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/10 to-blue-500/10">
              <Bot className="h-8 w-8 text-violet-500" />
            </div>
          }
          title="No conversations yet"
          description="Start a new AI chat to ask health-related questions."
          action={
            <Button onClick={() => setNewChatOpen(true)} className="shadow-sm">
              <Sparkles className="h-4 w-4 mr-1.5" />
              Start First Chat
            </Button>
          }
        />
      ) : (
        <div className="space-y-2">
          {filteredConversations.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No conversations match your search
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const memberName = conv.family_member_id
                ? memberMap.get(conv.family_member_id)
                : null;
              return (
                <Card
                  key={conv.id}
                  className="group hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
                >
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center gap-3">
                      <Link
                        to={`/conversations/${conv.id}`}
                        className="flex-1 min-w-0 flex items-center gap-3"
                      >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20">
                          <Bot className="h-4.5 w-4.5 text-violet-600 dark:text-violet-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium truncate">
                            {conv.title || "Untitled Conversation"}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <Badge variant="outline" className="text-[10px]">
                              {conv.scope === "member" ? (
                                <span className="flex items-center gap-1">
                                  <User className="h-2.5 w-2.5" />
                                  {memberName || "Member"}
                                </span>
                              ) : (
                                "General"
                              )}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {relativeTime(conv.updated_at)}
                            </span>
                          </div>
                        </div>
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                        aria-label="Delete conversation"
                        onClick={() => {
                          setDeleteId(conv.id);
                          setDeleteOpen(true);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
      )}

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
