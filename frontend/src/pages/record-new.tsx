import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { listProviders } from "@/lib/api/providers";
import { createRecord } from "@/lib/api/records";
import { RecordForm } from "@/components/records/record-form";
import { RecordFormWizard } from "@/components/records/wizard/record-form-wizard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import useSWR from "swr";
import type { HealthRecordCreate, HealthRecordResponse } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";

const FORM_MODE_KEY = "record-form-mode";

interface ActionResult {
  error?: string;
  success?: boolean;
  record?: HealthRecordResponse;
  prescriptions?: Record<string, string>[];
}

export default function NewRecordPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const [searchParams] = useSearchParams();
  const defaultType = (searchParams.get("type") as RecordType) || undefined;
  const defaultProviderId = searchParams.get("provider_id") || undefined;
  const defaultChiefComplaint = searchParams.get("chief_complaint") || undefined;

  const [useWizard, setUseWizard] = useState(() => {
    const saved = localStorage.getItem(FORM_MODE_KEY);
    return saved !== "classic"; // default to wizard
  });

  const { data: providers = [] } = useSWR("providers", async () => {
    return listProviders().catch(() => []);
  });

  function createAction(mid: string) {
    return async function (_prevState: unknown, formData: FormData): Promise<ActionResult> {
      const data: HealthRecordCreate = {
        record_type: formData.get("record_type") as RecordType,
        record_date: formData.get("record_date") as string,
        record_time: (formData.get("record_time") as string) || null,
        clinical_data: formData.get("clinical_data") as string,
        diagnosis: (formData.get("diagnosis") as string) || null,
        prescription_text: (formData.get("prescription_text") as string) || null,
        provider_id: (formData.get("provider_id") as string) || null,
        next_review_date: (formData.get("next_review_date") as string) || null,
        tags: (() => {
          try {
            const v = JSON.parse(formData.get("tags") as string);
            return Array.isArray(v) ? v : null;
          } catch {
            return null;
          }
        })(),
      };
      const stagingFileIds = (formData.get("staging_file_ids") as string) || undefined;
      const originalFileNames = (formData.get("original_file_names") as string) || undefined;
      try {
        const record = await createRecord(mid, data, stagingFileIds, originalFileNames);
        // Check if record has prescriptions for medication sync dialog
        let prescriptions: Record<string, string>[] | undefined;
        try {
          const parsed = JSON.parse(data.clinical_data);
          if (parsed._type === "structured" && Array.isArray(parsed.prescriptions)) {
            prescriptions = parsed.prescriptions;
          }
        } catch {
          /* not structured */
        }
        return { success: true, record, prescriptions };
      } catch (e) {
        return { error: e instanceof Error ? e.message : "Failed to create record" };
      }
    };
  }

  if (!memberId) return null;
  const action = createAction(memberId);

  function toggleMode() {
    setUseWizard((prev) => {
      const next = !prev;
      localStorage.setItem(FORM_MODE_KEY, next ? "wizard" : "classic");
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to={`/people/${memberId}/records`} className="hover:underline">
          Records
        </Link>
        <span>/</span>
        <h1 className="text-2xl font-bold text-foreground">New Record</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Add Health Record</CardTitle>
        </CardHeader>
        <CardContent>
          {useWizard ? (
            <RecordFormWizard
              action={action}
              providers={providers}
              memberId={memberId}
              defaultType={defaultType}
              defaultProviderId={defaultProviderId}
              defaultChiefComplaint={defaultChiefComplaint}
              onSaveComplete={() => {
                /* stay on page — form resets itself */
              }}
            />
          ) : (
            <RecordForm
              action={action}
              providers={providers}
              memberId={memberId}
              defaultType={defaultType}
              defaultProviderId={defaultProviderId}
              defaultChiefComplaint={defaultChiefComplaint}
              onSaveComplete={() => {
                /* stay on page — form resets itself */
              }}
            />
          )}
        </CardContent>
      </Card>
      <div className="flex justify-center">
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-muted-foreground"
          onClick={toggleMode}
        >
          Switch to {useWizard ? "classic form" : "wizard"}
        </Button>
      </div>
    </div>
  );
}
