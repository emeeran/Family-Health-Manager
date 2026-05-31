import { useSearchParams } from "react-router-dom";
import { UnifiedChatLayout } from "@/components/conversations/unified-chat-layout";

export default function ConversationsPage() {
  const [searchParams] = useSearchParams();
  const conversationId = searchParams.get("conversationId") ?? undefined;
  const memberId = searchParams.get("memberId") ?? undefined;

  return (
    <div className="-m-4 md:-m-6 flex h-[calc(100vh-3.25rem)]">
      <UnifiedChatLayout initialConversationId={conversationId} initialMemberId={memberId} />
    </div>
  );
}
