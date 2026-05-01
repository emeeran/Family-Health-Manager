import useSWR from "swr";
import { listHouseholdRecords } from "@/lib/api/household";
import { listMembers } from "@/lib/api/members";
import {
  HouseholdRecordsContent,
  HouseholdRecordsSkeleton,
} from "@/app/(app)/records/household-records-content";
import { ErrorState } from "@/components/shared/error-state";

export default function HouseholdRecordsPage() {
  const { data, error, mutate } = useSWR("household-records-page", async () => {
    const [records, members] = await Promise.all([
      listHouseholdRecords().catch(() => []),
      listMembers().catch(() => []),
    ]);
    const memberNames: Record<string, string> = {};
    for (const m of members) memberNames[m.id] = `${m.first_name} ${m.last_name}`;
    return { records: records.filter((r) => !r.is_deleted), memberNames, members };
  });

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data) return <HouseholdRecordsSkeleton />;
  return (
    <HouseholdRecordsContent
      records={data.records}
      memberNames={data.memberNames}
      members={data.members}
    />
  );
}
