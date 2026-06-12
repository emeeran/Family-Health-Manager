import { useState, useEffect } from "react";
import useSWR from "swr";
import { listConversations, getConversation } from "@/lib/api/conversations";
import { listMembers } from "@/lib/api/members";
import type { ConversationResponse } from "@/lib/types/conversation";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { MessageResponse } from "@/lib/types/message";
import { ChatHeader } from "./chat-header";
import { ChatArea } from "./chat-area";
import { ConversationSidebarPanel } from "./conversation-sidebar-panel";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const SIDEBAR_COLLAPSED_KEY = "chat-sidebar-collapsed";

interface UnifiedChatLayoutProps {
  initialConversationId?: string;
  initialMemberId?: string;
  initialScope?: "general" | "member";
}

export function UnifiedChatLayout({
  initialConversationId,
  initialMemberId,
  initialScope,
}: UnifiedChatLayoutProps) {
  const [mode, setMode] = useState<"general" | "member">(
    initialScope === "member" || initialMemberId ? "member" : "general"
  );
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(initialMemberId ?? null);
  const [activeConvId, setActiveConvId] = useState<string | null>(initialConversationId ?? null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [convMessages, setConvMessages] = useState<MessageResponse[]>([]);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const { data: pageData, mutate: mutatePageData } = useSWR("conversations-page", async () => {
    const [conversations, members] = await Promise.all([
      listConversations(),
      listMembers().catch(() => []),
    ]);
    return { conversations, members };
  });

  const conversations: ConversationResponse[] = pageData?.conversations ?? [];
  const members: FamilyMemberResponse[] = pageData?.members ?? [];

  const { data: convData } = useSWR(
    activeConvId ? `conversation-${activeConvId}` : null,
    async () => {
      const data = await getConversation(activeConvId!);
      return data;
    },
    { revalidateOnFocus: false, dedupingInterval: 30_000 }
  );

  useEffect(() => {
    if (convData) {
      setConvMessages(convData.messages);
    }
  }, [convData]);

  function clearChat() {
    setActiveConvId(null);
    setConvMessages([]);
  }

  function findMostRecent(
    filter: (c: ConversationResponse) => boolean
  ): ConversationResponse | undefined {
    return conversations
      .filter(filter)
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0];
  }

  function handleModeChange(newMode: "general" | "member") {
    setMode(newMode);
    if (newMode === "general") {
      setSelectedMemberId(null);
      const existing = findMostRecent((c) => c.scope === "general");
      if (existing) {
        setActiveConvId(existing.id);
      } else {
        clearChat();
      }
    } else {
      if (selectedMemberId) {
        const existing = findMostRecent(
          (c) => c.scope === "member" && c.family_member_id === selectedMemberId
        );
        if (existing) {
          setActiveConvId(existing.id);
        } else {
          clearChat();
        }
      } else {
        clearChat();
      }
    }
  }

  function handleMemberChange(memberId: string | null) {
    setSelectedMemberId(memberId);
    if (memberId) {
      const existing = findMostRecent(
        (c) => c.scope === "member" && c.family_member_id === memberId
      );
      if (existing) {
        setActiveConvId(existing.id);
      } else {
        clearChat();
      }
    } else {
      clearChat();
    }
  }

  function handleSelectConversation(id: string) {
    setActiveConvId(id);
    setMobileSidebarOpen(false);
    const conv = conversations.find((c) => c.id === id);
    if (conv) {
      if (conv.scope === "member") {
        setMode("member");
        if (conv.family_member_id) setSelectedMemberId(conv.family_member_id);
      } else {
        setMode("general");
        setSelectedMemberId(null);
      }
    }
  }

  function handleConversationCreated(id: string) {
    setActiveConvId(id);
    mutatePageData();
  }

  function handleNewChat() {
    clearChat();
  }

  const sidebarContent = (
    <ConversationSidebarPanel
      conversations={conversations}
      members={members}
      activeConvId={activeConvId}
      onSelectConversation={handleSelectConversation}
      onNewChat={handleNewChat}
      onActiveDeleted={clearChat}
      onRefresh={() => mutatePageData()}
    />
  );

  if (!pageData) {
    return (
      <div className="flex items-center justify-center h-full bg-card">
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Desktop sidebar — ChatGPT-style collapsible */}
      <div
        className={cn(
          "hidden md:flex shrink-0 flex-col bg-card transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] overflow-hidden",
          sidebarCollapsed ? "w-[52px]" : "w-[280px]"
        )}
      >
        <div className={cn("h-full", sidebarCollapsed ? "w-[52px]" : "w-[280px]")}>
          <ConversationSidebarPanel
            conversations={conversations}
            members={members}
            activeConvId={activeConvId}
            onSelectConversation={handleSelectConversation}
            onNewChat={handleNewChat}
            onActiveDeleted={clearChat}
            onRefresh={() => mutatePageData()}
            collapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
          />
        </div>
      </div>

      {/* Mobile sidebar Sheet */}
      <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent side="left" className="w-[280px] p-0">
          {sidebarContent}
        </SheetContent>
      </Sheet>

      {/* Chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        <ChatHeader
          mode={mode}
          onModeChange={handleModeChange}
          selectedMemberId={selectedMemberId}
          onMemberChange={handleMemberChange}
          members={members}
          onToggleSidebar={() => setMobileSidebarOpen(true)}
        />
        <ChatArea
          conversationId={activeConvId}
          onConversationCreated={handleConversationCreated}
          scope={mode}
          familyMemberId={selectedMemberId}
          initialMessages={convMessages}
        />
      </div>
    </div>
  );
}
