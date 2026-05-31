import { useSearchParams } from "react-router-dom";
import { UnifiedChatLayout } from "@/components/conversations/unified-chat-layout";

export default function ConversationsPage() {
  const [searchParams] = useSearchParams();
  const conversationId = searchParams.get("conversationId") ?? undefined;
  const memberId = searchParams.get("memberId") ?? undefined;

  return (
    <div className="absolute inset-0 flex overflow-hidden">
      <UnifiedChatLayout initialConversationId={conversationId} initialMemberId={memberId} />
    </div>
  );
}
