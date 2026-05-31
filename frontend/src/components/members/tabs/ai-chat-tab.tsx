import { memo, useCallback } from "react";
import { MessageSquare, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { MemberDetailResponse } from "@/lib/types/member";

interface AiChatTabProps {
  data: MemberDetailResponse;
}

export const AiChatTab = memo(function AiChatTab({ data }: AiChatTabProps) {
  const { member } = data;
  const memberName = `${member.first_name} ${member.last_name}`;

  const handleOpenChat = useCallback(() => {
    window.open(`/conversations?memberId=${member.id}`, "_blank", "width=900,height=700");
  }, [member.id]);

  return (
    <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
      <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
        <MessageSquare className="h-6 w-6 text-primary" />
      </div>
      <div>
        <p className="text-sm font-medium">AI Chat — {memberName}</p>
        <p className="text-xs text-muted-foreground mt-1">
          Open the chat in a dedicated window for the full experience.
        </p>
      </div>
      <Button onClick={handleOpenChat} className="gap-2">
        <ExternalLink className="h-4 w-4" />
        Open Chat
      </Button>
    </div>
  );
});
