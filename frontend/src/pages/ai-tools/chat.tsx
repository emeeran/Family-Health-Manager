import { useSearchParams } from "react-router-dom";
import { UnifiedChatLayout } from "@/components/conversations/unified-chat-layout";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";

export default function AiToolsChatPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") ?? undefined;

  return (
    <AiToolsSubPage title="Chat Assistant">
      <div
        className="rounded-lg border bg-card overflow-hidden"
        style={{ height: "calc(100vh - 200px)", minHeight: 400 }}
      >
        <UnifiedChatLayout
          initialMemberId={memberId}
          initialScope={memberId ? "member" : undefined}
        />
      </div>
    </AiToolsSubPage>
  );
}
