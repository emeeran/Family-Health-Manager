import useSWR from "swr";
import { useParams } from "react-router-dom";
import { getLabRecords } from "@/lib/api/records";
import { getMember } from "@/lib/api/members";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { formatDate } from "@/lib/utils";
import { FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";

export default function LabRecordsPage() {
  const { memberId } = useParams<{ memberId: string }>();

  const { data, error, mutate } = useSWR(
    memberId ? [`lab-records`, memberId] : null,
    async ([, mid]) => {
      const [labData, member] = await Promise.all([getLabRecords(mid), getMember(mid)]);
      return { records: labData.items, member };
    }
  );

  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  const { records, member } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/members" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/members/${memberId}`} className="hover:underline">
          {member.first_name} {member.last_name}
        </Link>
        <span>/</span>
        <span className="text-foreground">Lab Records</span>
      </div>
      <h1 className="text-2xl font-bold">Lab Records</h1>
      {records.length === 0 ? (
        <EmptyState
          icon={<FlaskConical className="h-12 w-12" />}
          title="No lab records"
          description="Lab test results will appear here."
        />
      ) : (
        <div className="space-y-3">
          {records.map((record) => (
            <Card key={record.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-4 pb-4">
                <Link to={`/members/${memberId}/records/${record.id}`} className="block">
                  <div className="flex items-center gap-3 min-w-0">
                    <RecordTypeBadge type={record.record_type} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {formatDate(record.record_date)}
                        {record.provider_name ? ` — ${record.provider_name}` : ""}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {record.test_name || record.record_type.replace(/_/g, " ")}
                      </p>
                    </div>
                  </div>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
