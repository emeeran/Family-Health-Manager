import { memo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { MessageSquare, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { MemberDetailResponse } from "@/lib/types/member";

interface AiLaunchButtonsProps {
  data: MemberDetailResponse;
}

export const AiLaunchButtons = memo(function AiLaunchButtons({ data }: AiLaunchButtonsProps) {
  const { member } = data;
  const memberName = `${member.first_name} ${member.last_name}`;
  const navigate = useNavigate();

  const openChat = useCallback(() => {
    navigate(`/chat?scope=member&memberId=${member.id}`);
  }, [navigate, member.id]);

  const openAssistant = useCallback(() => {
    navigate(`/chat?scope=member&memberId=${member.id}`);
  }, [navigate, member.id]);

  return (
    <div className="grid gap-3 sm:grid-cols-2 mt-4">
      <Card className="shadow-none">
        <CardContent className="flex items-center gap-3 py-4">
          <div className="shrink-0 h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
            <MessageSquare className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">AI Chat</p>
            <p className="text-xs text-muted-foreground truncate">
              Chat about {memberName}&apos;s health records
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={openChat} className="shrink-0">
            Open
          </Button>
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardContent className="flex items-center gap-3 py-4">
          <div className="shrink-0 h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">AI Assistant</p>
            <p className="text-xs text-muted-foreground truncate">
              Insights, drug checks &amp; pre-consultation
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={openAssistant} className="shrink-0">
            Open
          </Button>
        </CardContent>
      </Card>
    </div>
  );
});
