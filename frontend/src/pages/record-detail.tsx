import useSWR from "swr";
import { useParams } from "react-router-dom";
import { getRecord } from "@/lib/api/records";
import { getMember } from "@/lib/api/members";
import { RecordDetailContent } from "@/app/(app)/members/[memberId]/records/[recordId]/record-detail-content";
import { ErrorState } from "@/components/shared/error-state";

export default function RecordDetailPage() {
  const { memberId, recordId } = useParams<{ memberId: string; recordId: string }>();

  const { data, error, mutate } = useSWR(
    memberId && recordId ? [`record`, memberId, recordId] : null,
    async ([, mid, rid]) => {
      const [record, member] = await Promise.all([getRecord(mid, rid), getMember(mid)]);
      return { record, member };
    }
  );

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <RecordDetailContent record={data.record} member={data.member} />;
}
