import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { serializeClinicalData } from "@/lib/clinical-data";
import { createRecord, regenerateSummary } from "@/lib/api/records";
import { simpleMarkdown } from "@/lib/markdown";
import { computeMedicationDiff, applyMedicationSync } from "@/lib/api/members";
import { MedicationSyncDialog } from "./medication-sync-dialog";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { toISODate } from "@/lib/utils";
import type { BatchExtractionItem, MedicationDiffResponse } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  AlertTriangle,
  Loader2,
  Save,
  SkipForward,
  Trash2,
  Eye,
} from "lucide-react";
import { toast } from "sonner";

export type CardStatus = "pending" | "editing" | "saving" | "saved" | "skipped" | "error";

interface BatchRecordCardProps {
  index: number;
  item: BatchExtractionItem;
  memberId: string;
  onStatusChange: (index: number, status: CardStatus) => void;
  onDelete?: (index: number) => void;
  defaultExpanded?: boolean;
}

const RECORD_TYPE_OPTIONS = Object.entries(RECORD_TYPE_LABELS) as [RecordType, string][];

function buildInitialData(item: BatchExtractionItem) {
  const ext = item.extracted;
  if (!ext) {
    return {
      record_type: "misc_record" as RecordType,
      record_date: "",
      diagnosis: "",
      clinical_data: "",
      prescription_text: "",
      next_review_date: "",
      provider_id: null as string | null,
      record_time: null as string | null,
      tags: null as string[] | null,
      chief_complaint: "",
      provider_name: "",
      prescription_count: 0,
      lab_test_count: 0,
      prescription_rows: [] as Record<string, string>[],
      lab_test_rows: [] as Record<string, string>[],
      readable_notes: "",
    };
  }

  const recordType = (ext.record_type || "misc_record") as RecordType;

  // Build structured clinical_data for the API (JSON with tables)
  const tableData: Record<string, Record<string, string>[]> = {};
  const prescriptionRows = (ext.prescriptions || []) as Record<string, string>[];
  const labTestRows = (ext.lab_tests || []) as Record<string, string>[];
  if (prescriptionRows.length > 0) tableData.prescriptions = prescriptionRows;
  if (labTestRows.length > 0) tableData.lab_tests = labTestRows;

  const customFields: Record<string, string> = {};
  if (ext.chief_complaint) customFields.chief_complaint = ext.chief_complaint;
  if (ext.existing_conditions) customFields.existing_conditions = ext.existing_conditions;
  if (ext.investigations) customFields.investigations = ext.investigations;

  const clinical_data =
    Object.keys(customFields).length > 0 || Object.keys(tableData).length > 0
      ? serializeClinicalData(recordType, customFields, tableData, ext.clinical_data || undefined)
      : ext.clinical_data || "{}";

  // Human-readable notes for display
  const readableParts: string[] = [];
  if (ext.chief_complaint) readableParts.push(`Chief Complaint: ${ext.chief_complaint}`);
  if (ext.clinical_data) readableParts.push(ext.clinical_data);
  if (ext.existing_conditions) readableParts.push(`Conditions: ${ext.existing_conditions}`);
  if (ext.investigations) readableParts.push(`Investigations: ${ext.investigations}`);
  if (prescriptionRows.length > 0) {
    readableParts.push(
      "Prescriptions:\n" +
        prescriptionRows
          .map(
            (r) => `  ${r.medicine || ""} ${r.dosage || ""} ${r.duration || ""} ${r.timing || ""}`
          )
          .join("\n")
    );
  }
  if (labTestRows.length > 0) {
    readableParts.push(
      "Lab Tests:\n" +
        labTestRows
          .map((r) => `  ${r.test_name || ""}: ${r.result || ""} (${r.ref_value || ""})`)
          .join("\n")
    );
  }

  return {
    record_type: recordType,
    record_date: ext.record_date || "",
    diagnosis: ext.diagnosis || "",
    clinical_data,
    prescription_text: ext.prescription_text || "",
    next_review_date: ext.next_review_date || "",
    provider_id: null as string | null,
    record_time: ext.record_time || null,
    tags: null as string[] | null,
    chief_complaint: ext.chief_complaint || "",
    provider_name: ext.provider_name || "",
    prescription_count: prescriptionRows.length,
    lab_test_count: labTestRows.length,
    prescription_rows: prescriptionRows,
    lab_test_rows: labTestRows,
    readable_notes: readableParts.join("\n\n"),
  };
}

export function BatchRecordCard({
  index,
  item,
  memberId,
  onStatusChange,
  onDelete,
  defaultExpanded,
}: BatchRecordCardProps) {
  const [status, setStatus] = useState<CardStatus>(item.error ? "error" : "pending");
  const [formData, setFormData] = useState(buildInitialData(item));
  const [error, setError] = useState<string | null>(item.error || null);
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const [summary, setSummary] = useState<string | null>(null);
  const [savedRecordId, setSavedRecordId] = useState<string | null>(null);
  const [summaryRegenerating, setSummaryRegenerating] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  // React to parent changing defaultExpanded (e.g. "Review Next" advancing)
  useEffect(() => {
    if (defaultExpanded !== undefined) setExpanded(defaultExpanded);
  }, [defaultExpanded]);

  // Scroll into view when expanded
  useEffect(() => {
    if (expanded && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [expanded]);
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [confirmDupSave, setConfirmDupSave] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [medDiff, setMedDiff] = useState<MedicationDiffResponse | null>(null);

  function updateField(field: string, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave() {
    if (item.is_duplicate && !confirmDupSave) {
      setConfirmDupSave(true);
      return;
    }

    if (!formData.record_date) {
      toast.error(`Record #${index + 1}: Date is required`);
      return;
    }

    setStatus("saving");
    setError(null);

    try {
      const dateISO = toISODate(formData.record_date) || formData.record_date;
      const nextReviewISO = formData.next_review_date
        ? toISODate(formData.next_review_date) || formData.next_review_date
        : null;

      const savedRecord = await createRecord(
        memberId,
        {
          record_type: formData.record_type,
          record_date: dateISO,
          record_time: formData.record_time,
          clinical_data: formData.clinical_data,
          diagnosis: formData.diagnosis || null,
          prescription_text: formData.prescription_text || null,
          next_review_date: nextReviewISO,
          provider_id: formData.provider_id,
          tags: formData.tags,
        },
        item.staging_file_id || undefined,
        item.filename
      );

      if (savedRecord.summary) {
        setSummary(savedRecord.summary);
      }
      setSavedRecordId(savedRecord.id);

      setStatus("saved");
      onStatusChange(index, "saved");
      toast.success(`Record #${index + 1} saved`);

      // Check for medication changes if this is a doctor visit with prescriptions
      if (formData.record_type === "doctor_visit" && formData.prescription_rows.length > 0) {
        try {
          const diffResult = await computeMedicationDiff(memberId, formData.prescription_rows);
          const hasChanges =
            diffResult.added.length + diffResult.updated.length + diffResult.removed.length > 0;
          if (hasChanges) {
            setMedDiff(diffResult);
          }
        } catch {
          // Medication diff is optional — don't block on failure
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to save record";
      setError(msg);
      setStatus("error");
      onStatusChange(index, "error");
    }
  }

  function handleSkip() {
    setStatus("skipped");
    onStatusChange(index, "skipped");
    setConfirmSkip(false);
  }

  // Render based on status
  const isSaved = status === "saved";
  const isSkipped = status === "skipped";
  const isSaving = status === "saving";

  const ext = item.extracted;
  const rxCount = ext?.prescriptions?.length || 0;
  const labCount = ext?.lab_tests?.length || 0;

  return (
    <>
      <div
        ref={cardRef}
        className={`rounded-lg border transition-all ${
          isSaved
            ? "border-emerald-200 bg-emerald-50/50"
            : isSkipped
              ? "border-gray-200 bg-gray-50 opacity-60"
              : item.is_duplicate
                ? "border-amber-200 bg-amber-50/30"
                : "border-gray-200 bg-white"
        }`}
      >
        {/* Header — clickable to expand */}
        <div
          className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none"
          onClick={() => !isSaved && !isSkipped && setExpanded(!expanded)}
        >
          {isSaved ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
          ) : isSkipped ? (
            <SkipForward className="h-5 w-5 text-gray-400 shrink-0" />
          ) : isSaving ? (
            <Loader2 className="h-5 w-5 animate-spin text-blue-500 shrink-0" />
          ) : (
            <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium truncate">{item.filename}</span>
              {ext?.record_type && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {RECORD_TYPE_LABELS[ext.record_type as RecordType] || ext.record_type}
                </Badge>
              )}
              {item.is_duplicate && (
                <Badge
                  variant="outline"
                  className="text-[10px] px-1.5 py-0 border-amber-400 text-amber-700 bg-amber-50"
                >
                  Duplicate
                </Badge>
              )}
              {item.verification && <VerificationBadge verification={item.verification} />}
            </div>
            <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
              {ext?.record_date && <span>{ext.record_date}</span>}
              {ext?.diagnosis && <span className="truncate max-w-[200px]">{ext.diagnosis}</span>}
              {rxCount > 0 && <span>{rxCount} Rx</span>}
              {labCount > 0 && <span>{labCount} labs</span>}
              {ext?.provider_name && <span>{ext.provider_name}</span>}
            </div>
          </div>

          {/* Action buttons */}
          {!isSaved && !isSkipped && (
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  setStatus("editing");
                  setExpanded(true);
                }}
                disabled={isSaving}
              >
                <Eye className="h-3 w-3 mr-1" />
                Review
              </Button>
              <Button
                size="sm"
                className="h-7 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={(e) => {
                  e.stopPropagation();
                  handleSave();
                }}
                disabled={isSaving}
              >
                {isSaving ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3 w-3 mr-1" />
                )}
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-red-500 hover:text-red-700 hover:bg-red-50"
                onClick={(e) => {
                  e.stopPropagation();
                  setConfirmDelete(true);
                }}
                disabled={isSaving}
              >
                <Trash2 className="h-3 w-3 mr-1" />
                Delete
              </Button>
              {!expanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground ml-1" />
              ) : (
                <ChevronUp className="h-4 w-4 text-muted-foreground ml-1" />
              )}
            </div>
          )}

          {isSaved && <span className="text-xs text-emerald-600 font-medium">Saved</span>}
          {isSkipped && <span className="text-xs text-gray-400">Skipped</span>}
        </div>

        {/* Summary section — shown after save */}
        {isSaved && summary && (
          <details
            className="mx-4 mb-3 rounded-lg border border-emerald-200 bg-white overflow-hidden"
            open
          >
            <summary className="px-3 py-2 text-xs font-semibold text-emerald-800 bg-emerald-50 cursor-pointer select-none flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              Consultation Summary
            </summary>
            <div className="px-3 py-2">
              <div
                className="text-xs text-gray-700 prose prose-sm max-w-none prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-th:bg-gray-50"
                dangerouslySetInnerHTML={{ __html: simpleMarkdown(summary) }}
              />
              <div className="mt-2 pt-2 border-t border-gray-100 flex items-center gap-2">
                {savedRecordId && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 text-[10px]"
                    onClick={async () => {
                      if (!savedRecordId) return;
                      setSummaryRegenerating(true);
                      try {
                        const result = await regenerateSummary(memberId, savedRecordId);
                        if (result.summary) {
                          setSummary(result.summary);
                          toast.success("Summary regenerated");
                        }
                      } catch {
                        toast.error("Failed to regenerate summary");
                      } finally {
                        setSummaryRegenerating(false);
                      }
                    }}
                    disabled={summaryRegenerating}
                  >
                    {summaryRegenerating ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
                    Regenerate
                  </Button>
                )}
              </div>
            </div>
          </details>
        )}
        {error && !isSaved && !isSkipped && (
          <div className="px-4 pb-2 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-600">{error}</p>
          </div>
        )}

        {/* Duplicate warning */}
        {item.is_duplicate && !isSaved && !isSkipped && (
          <div className="px-4 pb-2 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              Potential duplicate of existing record
              {item.duplicate_of_diagnosis ? ` (${item.duplicate_of_diagnosis})` : ""}
            </p>
          </div>
        )}

        {/* Expanded edit form */}
        {expanded && !isSaved && !isSkipped && (
          <div className="px-4 pb-4 pt-2 border-t border-gray-100 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Record Type</Label>
                <Select
                  value={formData.record_type}
                  onValueChange={(v) => {
                    if (v) updateField("record_type", v);
                  }}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECORD_TYPE_OPTIONS.map(([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Date</Label>
                <Input
                  className="h-8 text-xs"
                  value={formData.record_date}
                  onChange={(e) => updateField("record_date", e.target.value)}
                  placeholder="DD-MM-YYYY"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Diagnosis</Label>
              <Input
                className="h-8 text-xs"
                value={formData.diagnosis}
                onChange={(e) => updateField("diagnosis", e.target.value)}
                placeholder="Diagnosis"
              />
            </div>

            {formData.chief_complaint && (
              <div>
                <Label className="text-xs">Chief Complaint</Label>
                <Input
                  className="h-8 text-xs"
                  value={formData.chief_complaint}
                  onChange={(e) => updateField("chief_complaint", e.target.value)}
                />
              </div>
            )}

            {formData.provider_name && (
              <div>
                <Label className="text-xs">Provider</Label>
                <Input
                  className="h-8 text-xs"
                  value={formData.provider_name}
                  onChange={(e) => updateField("provider_name", e.target.value)}
                />
              </div>
            )}

            {formData.prescription_count > 0 && (
              <div>
                <Label className="text-xs">Prescriptions ({formData.prescription_count})</Label>
                <div className="rounded border text-xs divide-y">
                  {formData.prescription_rows.map((rx, ri) => (
                    <div key={ri} className="flex gap-2 px-2 py-1">
                      <span className="font-medium">{rx.medicine}</span>
                      <span className="text-muted-foreground">{rx.dosage}</span>
                      <span className="text-muted-foreground">{rx.duration}</span>
                      {rx.timing && (
                        <span className="text-muted-foreground">
                          {rx.timing.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {formData.lab_test_count > 0 && (
              <div>
                <Label className="text-xs">Lab Tests ({formData.lab_test_count})</Label>
                <div className="rounded border text-xs divide-y">
                  {formData.lab_test_rows.map((lt, ri) => (
                    <div key={ri} className="flex gap-2 px-2 py-1">
                      <span className="font-medium">{lt.test_name}</span>
                      <span>{lt.result}</span>
                      {lt.ref_value && (
                        <span className="text-muted-foreground">({lt.ref_value})</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {formData.readable_notes && (
              <div>
                <Label className="text-xs">Notes</Label>
                <Textarea
                  className="text-xs min-h-[60px]"
                  value={formData.readable_notes}
                  onChange={(e) => updateField("readable_notes", e.target.value)}
                />
              </div>
            )}

            <div>
              <Label className="text-xs">Next Review Date</Label>
              <Input
                className="h-8 text-xs"
                value={formData.next_review_date}
                onChange={(e) => updateField("next_review_date", e.target.value)}
                placeholder="DD-MM-YYYY"
              />
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button
                size="sm"
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={handleSave}
                disabled={isSaving}
              >
                {isSaving ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5 mr-1" />
                )}
                {isSaving ? "Saving..." : "Save Record"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setExpanded(false)}>
                Collapse
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Skip confirmation */}
      <Dialog open={confirmSkip} onOpenChange={setConfirmSkip}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Skip this record?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Skip &quot;{item.filename}&quot;? This file will not be saved as a record.
          </p>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setConfirmSkip(false)}>
              Cancel
            </Button>
            <Button size="sm" variant="destructive" onClick={handleSkip}>
              Skip
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Duplicate save confirmation */}
      <Dialog open={confirmDupSave} onOpenChange={setConfirmDupSave}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Potential Duplicate</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This record may duplicate an existing record
            {item.duplicate_of_diagnosis ? ` (${item.duplicate_of_diagnosis})` : ""}. Save anyway?
          </p>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setConfirmDupSave(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setConfirmDupSave(false);
                handleSave();
              }}
            >
              Save Anyway
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete this record?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Remove &quot;{item.filename}&quot; from the queue? This cannot be undone.
          </p>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                setConfirmDelete(false);
                onDelete?.(index);
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Medication sync dialog */}
      {medDiff && (
        <MedicationSyncDialog
          open={!!medDiff}
          onOpenChange={(open) => {
            if (!open) setMedDiff(null);
          }}
          diff={medDiff}
          onApply={async (applyAdded, applyUpdated, applyRemoved) => {
            await applyMedicationSync(memberId, applyAdded, applyUpdated, applyRemoved);
            setMedDiff(null);
          }}
        />
      )}
    </>
  );
}
