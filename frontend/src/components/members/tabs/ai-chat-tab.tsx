import { memo } from "react";
import type { MemberDetailResponse } from "@/lib/types/member";
import { MemberChat } from "./member-chat";

interface AiChatTabProps {
  data: MemberDetailResponse;
}

export const AiChatTab = memo(function AiChatTab({ data }: AiChatTabProps) {
  const { member } = data;
  return (
    <MemberChat memberId={member.id} memberName={`${member.first_name} ${member.last_name}`} />
  );
});
