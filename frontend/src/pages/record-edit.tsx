import useSWR, { mutate } from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getRecord } from "@/lib/api/records";
import { listProviders } from "@/lib/api/providers";
import { updateRecord } from "@/lib/api/records";
import { RecordForm } from "@/components/records/record-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { HealthRecordUpdate } from "@/lib/types/health-record";
import { ErrorState } from "@/components/shared/error-state";

export default function EditRecordPage() {
  const { memberId, recordId } = useParams<{ memberId: string; recordId: string }>();
  const navigate = useNavigate();

  const {
    data,
    error,
    mutate: _revalidate,
  } = useSWR(
    memberId && recordId ? [`record-edit`, memberId, recordId] : null,
    async ([, mid, rid]) => {
      const [record, providers] = await Promise.all([getRecord(mid, rid), listProviders()]);
      return { record, providers };
    }
  );

  function createAction(mid: string, rid: string) {
    return async function (prevState: unknown, formData: FormData) {
      // Build update payload — only include fields present in the form.
      // Use `exclude_unset` semantics: don't send null for fields
      // that simply weren't rendered (avoids clearing existing data).
      const data: HealthRecordUpdate = {};

      const clinicalData = formData.get("clinical_data") as string;
      if (clinicalData) data.clinical_data = clinicalData;

      const diagnosis = formData.get("diagnosis") as string;
      if (diagnosis !== null) data.diagnosis = diagnosis || null;

      const prescriptionText = formData.get("prescription_text") as string;
      // prescription_text may not be in the form at all (e.g. doctor_visit).
      // Only include it if the form actually has the field.
      if (prescriptionText !== null) data.prescription_text = prescriptionText || null;

      const providerId = formData.get("provider_id") as string;
      if (providerId !== null) data.provider_id = providerId || null;

      const nextReviewDate = formData.get("next_review_date") as string;
      if (nextReviewDate !== null) data.next_review_date = nextReviewDate || null;

      try {
        const tagsRaw = formData.get("tags") as string;
        if (tagsRaw !== null) {
          try {
            const v = JSON.parse(tagsRaw);
            data.tags = Array.isArray(v) ? v : null;
          } catch {
            data.tags = null;
          }
        }

        await updateRecord(mid, rid, data);

        // Invalidate all relevant caches so the detail page shows fresh data
        mutate(`member-dashboard-${mid}`);
        mutate(["record", mid, rid]);
        mutate(["record-edit", mid, rid]);
        mutate("dashboard");

        navigate(`/members/${mid}/records/${rid}`);
        return null;
      } catch (e) {
        return { error: e instanceof Error ? e.message : "Failed to update record" };
      }
    };
  }

  if (error) return <ErrorState onRetry={() => _revalidate()} />;
  if (!data || !memberId || !recordId)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  const action = createAction(memberId, recordId);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to={`/members/${memberId}/records/${recordId}`} className="hover:underline">
          Record
        </Link>
        <span>/</span>
        <h1 className="text-2xl font-bold text-foreground">Edit Record</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Edit Health Record</CardTitle>
        </CardHeader>
        <CardContent>
          <RecordForm action={action} providers={data.providers} record={data.record} />
        </CardContent>
      </Card>
    </div>
  );
}
