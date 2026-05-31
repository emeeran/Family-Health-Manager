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

interface UnifiedChatLayoutProps {
  initialConversationId?: string;
  initialMemberId?: string;
}

export function UnifiedChatLayout({
  initialConversationId,
  initialMemberId,
}: UnifiedChatLayoutProps) {
  const [mode, setMode] = useState<"general" | "member">(initialMemberId ? "member" : "general");
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(initialMemberId ?? null);
  const [activeConvId, setActiveConvId] = useState<string | null>(initialConversationId ?? null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [convMessages, setConvMessages] = useState<MessageResponse[]>([]);

  // Fetch conversations + members
  const { data: pageData, mutate: mutatePageData } = useSWR("conversations-page", async () => {
    const [conversations, members] = await Promise.all([
      listConversations(),
      listMembers().catch(() => []),
    ]);
    return { conversations, members };
  });

  const conversations: ConversationResponse[] = pageData?.conversations ?? [];
  const members: FamilyMemberResponse[] = pageData?.members ?? [];

  // Fetch active conversation messages
  const { data: convData } = useSWR(
    activeConvId ? `conversation-${activeConvId}` : null,
    async () => {
      const data = await getConversation(activeConvId!);
      return data;
    },
    { revalidateOnFocus: false, dedupingInterval: 30_000 }
  );

  // Sync conversation data to local state
  useEffect(() => {
    if (convData) {
      setConvMessages(convData.messages);
    }
  }, [convData]);

  function clearChat() {
    setActiveConvId(null);
    setConvMessages([]);
  }

  function handleModeChange(newMode: "general" | "member") {
    setMode(newMode);
    if (newMode === "general") {
      setSelectedMemberId(null);
      const existing = conversations.find((c) => c.scope === "general");
      if (existing) {
        setActiveConvId(existing.id);
      } else {
        clearChat();
      }
    } else {
      if (selectedMemberId) {
        const existing = conversations.find(
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
      const existing = conversations.find(
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
    setSidebarOpen(false);
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
    />
  );

  if (!pageData) {
    return (
      <div className="flex items-center justify-center h-full">
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <div className="hidden md:flex w-[260px] shrink-0 border-r">{sidebarContent}</div>

      {/* Mobile sidebar Sheet */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
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
          onToggleSidebar={() => setSidebarOpen(true)}
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
