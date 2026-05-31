import useSWR from "swr";
import { useParams, Link } from "react-router-dom";
import { getMemberDetail } from "@/lib/api/members";
import { AiAssistantTab } from "@/components/members/tabs/ai-assistant-tab";
import { ArrowLeft } from "lucide-react";

export default function MemberAssistantPage() {
  const { memberId } = useParams<{ memberId: string }>();

  const { data: detail } = useSWR(
    memberId ? `member-detail-${memberId}` : null,
    async () => getMemberDetail(memberId!),
    { revalidateOnMount: true, dedupingInterval: 60_000 }
  );

  if (!detail) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const memberName = `${detail.member.first_name} ${detail.member.last_name}`;

  return (
    <div className="space-y-4">
      <Link
        to={`/members/${memberId}`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to {memberName}
      </Link>
      <h1 className="text-lg font-semibold">AI Assistant — {memberName}</h1>
      <AiAssistantTab data={detail} />
    </div>
  );
}
