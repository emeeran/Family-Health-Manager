import useSWR from "swr";
import { listMembers } from "@/lib/api/members";
import { MembersContent } from "@/app/(app)/members/members-content";
import { ErrorState } from "@/components/shared/error-state";

export default function MembersPage() {
  const {
    data: members,
    error,
    mutate,
  } = useSWR("members", async () => {
    return listMembers();
  });

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!members)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <MembersContent members={members} />;
}
