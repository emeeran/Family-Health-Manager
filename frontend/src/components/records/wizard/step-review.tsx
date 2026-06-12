import { memo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, RotateCcw, FileText } from "lucide-react";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";
import type { RecordTypeConfig } from "@/lib/record-type-configs";

interface StepReviewProps {
  recordType: RecordType | undefined;
  recordDate: string;
  recordTime?: string;
  providerName: string | null;
  chiefComplaint?: string;
  diagnosis: string | null;
  customValues: Record<string, string>;
  tableData: Record<string, Record<string, string>[]>;
  notes: string;
  tags: string[];
  uploadedFiles: { name: string }[];
  config: RecordTypeConfig | null;
  isDoctorVisit: boolean;
  isPending: boolean;
  isEditing: boolean;
  onSubmit: () => void;
  onReset: () => void;
}

function ReviewRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className="text-xs font-medium text-right">{value}</span>
    </div>
  );
}

export const StepReview = memo(function StepReview({
  recordType,
  recordDate,
  recordTime,
  providerName,
  chiefComplaint,
  diagnosis,
  customValues,
  tableData,
  notes,
  tags,
  uploadedFiles,
  config,
  isDoctorVisit,
  isPending,
  isEditing,
  onSubmit,
  onReset,
}: StepReviewProps) {
  const typeLabel = recordType
    ? (RECORD_TYPE_LABELS as Record<string, string>)[recordType] || recordType
    : "—";

  // Count prescriptions for preview
  const prescriptionRows = (tableData["prescriptions"] || []).filter((row) => row.medicine?.trim());

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Review & Save
      </p>

      <Card className="border">
        <CardContent className="p-3 space-y-1">
          <ReviewRow
            label="Type"
            value={
              <Badge variant="outline" className="text-xs">
                {typeLabel}
              </Badge>
            }
          />
          <ReviewRow label="Date" value={recordDate || "—"} />
          {recordTime && <ReviewRow label="Time" value={recordTime} />}
          {providerName && <ReviewRow label="Provider" value={providerName} />}
          {isDoctorVisit && chiefComplaint && (
            <ReviewRow label="Complaint" value={chiefComplaint} />
          )}
          {diagnosis && <ReviewRow label="Diagnosis" value={diagnosis} />}

          {/* Custom values (non-doctor-visit) */}
          {!isDoctorVisit &&
            config &&
            config.customFields.map((field) => {
              const val = customValues[field.key];
              if (!val) return null;
              return <ReviewRow key={field.key} label={field.label} value={val} />;
            })}

          {/* Prescription count */}
          {prescriptionRows.length > 0 && (
            <ReviewRow
              label="Prescriptions"
              value={`${prescriptionRows.length} medication${prescriptionRows.length !== 1 ? "s" : ""}`}
            />
          )}

          {/* Lab results count */}
          {(tableData["tests"] || tableData["lab_results"] || []).length > 0 && (
            <ReviewRow
              label="Lab Tests"
              value={`${(tableData["tests"] || tableData["lab_results"]).length} test${(tableData["tests"] || tableData["lab_results"]).length !== 1 ? "s" : ""}`}
            />
          )}

          {notes && <ReviewRow label="Notes" value={notes} />}
        </CardContent>
      </Card>

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <Badge key={t} variant="secondary" className="text-xs">
              {t}
            </Badge>
          ))}
        </div>
      )}

      {/* File attachments */}
      {uploadedFiles.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Attachments
          </p>
          <div className="flex flex-wrap gap-1.5">
            {uploadedFiles.map((f, i) => (
              <Badge key={i} variant="outline" className="text-xs gap-1">
                <FileText className="h-3 w-3" />
                {f.name}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-2">
        {!isEditing && (
          <Button type="button" variant="outline" size="sm" onClick={onReset} disabled={isPending}>
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            Clear
          </Button>
        )}
        <Button type="button" disabled={isPending} size="sm" onClick={onSubmit}>
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {isPending ? "Saving..." : isEditing ? "Update Record" : "Create Record"}
        </Button>
      </div>
    </div>
  );
});
