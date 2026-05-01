import useSWR from "swr";
import { useParams } from "react-router-dom";
import { listRecords } from "@/lib/api/records";
import { getMember } from "@/lib/api/members";
import { RecordsListContent } from "@/app/(app)/members/[memberId]/records/records-list-content";
import { ErrorState } from "@/components/shared/error-state";
export default function MemberRecordsPage() {
  const { memberId } = useParams<{ memberId: string }>();

  const { data, error, mutate } = useSWR(
    memberId ? [`member-records`, memberId] : null,
    async ([, mid]) => {
      const [records, member] = await Promise.all([listRecords(mid), getMember(mid)]);
      return { records, member };
    }
  );

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <RecordsListContent records={data.records} member={data.member} onRefresh={mutate} />;
}
