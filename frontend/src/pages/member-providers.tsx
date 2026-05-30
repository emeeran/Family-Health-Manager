import useSWR from "swr";
import { useParams } from "react-router-dom";
import { listAssignments } from "@/lib/api/provider-assignments";
import { listProviders } from "@/lib/api/providers";
import { getMember } from "@/lib/api/members";
import { MemberProvidersContent } from "@/components/content/member-providers-content";
import { ErrorState } from "@/components/shared/error-state";

export default function MemberProvidersPage() {
  const { memberId } = useParams<{ memberId: string }>();

  const { data, error, mutate } = useSWR(
    memberId ? [`member-providers`, memberId] : null,
    async ([, mid]) => {
      const [assignments, providers, member] = await Promise.all([
        listAssignments(mid),
        listProviders(),
        getMember(mid),
      ]);
      return { assignments, providers, member };
    }
  );

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return (
    <MemberProvidersContent
      assignments={data.assignments}
      providers={data.providers}
      member={data.member}
    />
  );
}
