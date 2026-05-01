import useSWR from "swr";
import { listConversations } from "@/lib/api/conversations";
import { listMembers } from "@/lib/api/members";
import { ConversationsContent } from "@/app/(app)/conversations/conversations-content";
import { ErrorState } from "@/components/shared/error-state";

export default function ConversationsPage() {
  const { data, error, mutate } = useSWR("conversations-page", async () => {
    const [conversations, members] = await Promise.all([
      listConversations(),
      listMembers().catch(() => []),
    ]);
    return { conversations, members };
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <ConversationsContent conversations={data.conversations} members={data.members} />;
}
