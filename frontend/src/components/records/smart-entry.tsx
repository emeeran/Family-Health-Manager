import { useState, useRef, useCallback } from "react";
import { Upload, Loader2, Check, Sparkles, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { parseNaturalLanguage, createRecord, extractFromDocument } from "@/lib/api/records";
import type { NLParseResponse } from "@/lib/api/records";
import type { ExtractionResponse } from "@/lib/types/health-record";
import { MemberPicker } from "@/components/shared/member-picker";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { todayISO, nowTime } from "@/lib/quick-record";
import type { RecordType } from "@/lib/types/enums";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import {
  validatePrescriptionRow,
  validateLabTestRow,
  normalizeDate,
  normalizeTime,
  VALID_RECORD_TYPES,
} from "@/components/records/record-form-utils";
import { MedicationSyncDialog } from "@/components/records/medication-sync-dialog";
import { computeMedicationDiff, applyMedicationSync } from "@/lib/api/members";
import type { MedicationDiffResponse } from "@/lib/types/health-record";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

interface SmartEntryBarProps {
  members: { id: string; first_name: string; last_name: string; is_active: boolean }[];
}

type Step = "input" | "confirm" | "saving";

/* ------------------------------------------------------------------ */
/*  SmartEntryBar — Compact single-line input                           */
/* ------------------------------------------------------------------ */

export function SmartEntryBar({ members }: SmartEntryBarProps) {
  const { mutate } = useSWRConfig();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedMemberId, setSelectedMemberId] = useState<string>("");
  const [step, setStep] = useState<Step>("input");

  // Text input
  const [input, setInput] = useState("");
  const [parsed, setParsed] = useState<NLParseResponse | null>(null);

  // Upload
  const [extracting, setExtracting] = useState(false);
  const [extractedData, setExtractedData] = useState<ExtractionResponse | null>(null);

  // Confirmation fields
  const [recordType, setRecordType] = useState<RecordType>("misc_record");
  const [recordDate, setRecordDate] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [prescriptionText, setPrescriptionText] = useState("");
  const [clinicalNotes, setClinicalNotes] = useState("");
  const [saving, setSaving] = useState(false);

  // Medication sync
  const [medSyncDiff, setMedSyncDiff] = useState<MedicationDiffResponse | null>(null);
  const [showMedSyncDialog, setShowMedSyncDialog] = useState(false);

  const activeMembers = members.filter((m) => m.is_active);

  /* ── NL Text parse ── */
  const handleParse = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    try {
      const result = await parseNaturalLanguage(text);
      setParsed(result);
      if (result.member) setSelectedMemberId(result.member.id);
      setRecordType(
        VALID_RECORD_TYPES.has(result.record_type ?? "")
          ? (result.record_type as RecordType)
          : "misc_record"
      );
      setRecordDate(normalizeDate(result.record_date) || todayISO());
      setDiagnosis(result.diagnosis || "");
      setPrescriptionText(result.prescription_text || "");
      setClinicalNotes(result.clinical_notes || "");
      setStep("confirm");
    } catch {
      toast.error("Couldn't parse that. Try rephrasing or upload a document.");
    }
  }, [input]);

  /* ── File upload + OCR ── */
  const processFile = useCallback(
    async (file: File) => {
      const memberId = selectedMemberId || activeMembers[0]?.id;
      if (!memberId) {
        toast.error("Please select a family member first");
        return;
      }
      setExtracting(true);
      toast.info(`Processing ${file.name}...`);
      try {
        const response = await extractFromDocument(memberId, file);
        setExtractedData(response);
        setSelectedMemberId(memberId);
        setRecordType(
          VALID_RECORD_TYPES.has(response.extracted.record_type ?? "")
            ? (response.extracted.record_type as RecordType)
            : "misc_record"
        );
        setRecordDate(normalizeDate(response.extracted.record_date) || todayISO());
        setDiagnosis(response.extracted.diagnosis || "");
        setPrescriptionText(response.extracted.prescription_text || "");
        setClinicalNotes(response.extracted.clinical_data || "");
        setStep("confirm");
        toast.success("Document extraction complete!");
      } catch {
        toast.error("AI extraction failed. Try another document or log manually.");
      } finally {
        setExtracting(false);
      }
    },
    [selectedMemberId, activeMembers]
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.[0]) processFile(e.target.files[0]);
    },
    [processFile]
  );

  /* ── Save ── */
  const handleSave = useCallback(async () => {
    if (!selectedMemberId) return;
    setSaving(true);
    try {
      // Build structured clinical_data when prescriptions were extracted from a document
      let clinicalDataValue = clinicalNotes;
      let validatedPrescriptions: Record<string, string>[] = [];
      const rawPrescriptions = extractedData?.extracted?.prescriptions;
      if (rawPrescriptions && rawPrescriptions.length > 0) {
        validatedPrescriptions = rawPrescriptions
          .map(validatePrescriptionRow)
          .filter((r): r is Record<string, string> => r !== null);
        const structured: Record<string, unknown> = {
          _type: "structured",
          _version: 1,
          _recordType: recordType,
        };
        if (clinicalNotes) structured._notes = clinicalNotes;
        if (validatedPrescriptions.length > 0) structured.prescriptions = validatedPrescriptions;
        const rawLabTests = extractedData?.extracted?.lab_tests;
        if (rawLabTests && rawLabTests.length > 0) {
          const labTests = rawLabTests
            .map(validateLabTestRow)
            .filter((r): r is Record<string, string> => r !== null);
          if (labTests.length > 0) structured.lab_tests = labTests;
        }
        clinicalDataValue = JSON.stringify(structured);
      }

      const record = await createRecord(
        selectedMemberId,
        {
          record_type: recordType,
          record_date: recordDate || todayISO(),
          record_time: normalizeTime(extractedData?.extracted.record_time) || nowTime(),
          clinical_data: clinicalDataValue,
          diagnosis: diagnosis || null,
          prescription_text: prescriptionText || null,
          provider_id: null,
          next_review_date: normalizeDate(extractedData?.extracted.next_review_date) || null,
          tags: null,
        },
        extractedData?.staging_file_id || undefined,
        extractedData?.original_file_name || undefined
      );

      toast.success("Record saved!");

      // Check for medication sync if we sent structured prescriptions
      if (validatedPrescriptions.length > 0) {
        try {
          const diff = await computeMedicationDiff(
            selectedMemberId,
            validatedPrescriptions,
            record.id
          );
          const totalChanges = diff.added.length + diff.updated.length + diff.removed.length;
          if (totalChanges > 0) {
            setMedSyncDiff(diff);
            setShowMedSyncDialog(true);
            await Promise.all([
              mutate("dashboard"),
              mutate("members"),
              mutate(`member-detail-${selectedMemberId}`),
            ]);
            return; // Don't reset yet — wait for dialog
          }
        } catch (err) {
          // Non-critical — medication sync is best-effort
          console.error("Medication diff failed:", err);
        }
      }

      resetState();
      await Promise.all([
        mutate("dashboard"),
        mutate("members"),
        mutate(`member-detail-${selectedMemberId}`),
      ]);
    } catch {
      toast.error("Failed to save health record");
    } finally {
      setSaving(false);
    }
  }, [
    selectedMemberId,
    recordType,
    recordDate,
    diagnosis,
    prescriptionText,
    clinicalNotes,
    extractedData,
    mutate,
  ]);

  function resetState() {
    setStep("input");
    setInput("");
    setParsed(null);
    setExtractedData(null);
    setRecordType("misc_record");
    setRecordDate("");
    setDiagnosis("");
    setPrescriptionText("");
    setClinicalNotes("");
    setMedSyncDiff(null);
    setShowMedSyncDialog(false);
  }

  return (
    <>
      {/* Compact single-line bar */}
      <div className="flex items-center gap-2 rounded-xl border shadow-sm bg-card p-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-accent)]/10 text-[var(--brand-accent)]">
          <Activity className="h-4 w-4" />
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleParse();
          }}
          className="flex flex-1 items-center gap-2"
        >
          <Input
            placeholder='Describe: "dad visited doctor, prescribed metformin 500mg" or "blood sugar 120"'
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="flex-1 h-9 text-sm focus-visible:ring-[var(--brand-accent)]/30"
            disabled={extracting}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf"
            className="hidden"
            onChange={handleFileChange}
            disabled={extracting}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 gap-1.5 shrink-0"
            onClick={() => fileInputRef.current?.click()}
            disabled={extracting}
          >
            {extracting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            <span className="hidden sm:inline">Upload</span>
          </Button>
          <Button
            type="submit"
            size="sm"
            disabled={!input.trim()}
            className="h-9 shrink-0 bg-[var(--brand-accent)] text-white hover:bg-[var(--brand-accent)]/90"
          >
            Parse
          </Button>
        </form>
        <MemberPicker
          members={members}
          value={selectedMemberId}
          onChange={setSelectedMemberId}
          size="sm"
        />
      </div>

      {/* Confirmation Dialog */}
      <Dialog
        open={step === "confirm"}
        onOpenChange={(open) => {
          if (!open) resetState();
        }}
      >
        <DialogContent className="max-w-lg w-full max-h-[85vh] overflow-y-auto">
          <DialogHeader className="pb-2 border-b">
            <div className="flex items-center justify-between">
              <DialogTitle className="text-base font-bold flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                Review Details
              </DialogTitle>
              {(parsed?.confidence || extractedData?.confidence) && (
                <Badge
                  variant={
                    (parsed?.confidence || extractedData?.confidence) === "high"
                      ? "default"
                      : "outline"
                  }
                  className="text-[10px] font-bold"
                >
                  {parsed?.confidence || extractedData?.confidence} confidence
                </Badge>
              )}
            </div>
          </DialogHeader>

          <div className="space-y-4 py-3 text-sm">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Family Member</label>
              <MemberPicker
                members={members}
                value={selectedMemberId}
                onChange={setSelectedMemberId}
                size="md"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">Record Type</label>
                <select
                  value={recordType}
                  onChange={(e) => setRecordType(e.target.value as RecordType)}
                  className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-xs focus:ring-1 focus:ring-primary/20 focus:outline-none"
                >
                  {Object.entries(RECORD_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">Record Date</label>
                <Input
                  type="date"
                  value={recordDate}
                  onChange={(e) => setRecordDate(e.target.value)}
                  className="h-8 text-xs bg-background"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Diagnosis</label>
              <Input
                placeholder="e.g. Type 2 Diabetes"
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
                className="h-8 text-xs bg-background"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Prescriptions</label>
              <textarea
                placeholder="e.g. Metformin 500mg - 1-0-1 - 3 months"
                value={prescriptionText}
                onChange={(e) => setPrescriptionText(e.target.value)}
                rows={2}
                className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-xs focus:ring-1 focus:ring-primary/20 focus:outline-none placeholder:text-muted-foreground/45"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">
                Clinical Details
              </label>
              <textarea
                placeholder="Doctor's advice, vitals, lab readings..."
                value={clinicalNotes}
                onChange={(e) => setClinicalNotes(e.target.value)}
                rows={4}
                className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-xs focus:ring-1 focus:ring-primary/20 focus:outline-none placeholder:text-muted-foreground/45"
              />
            </div>
          </div>

          <DialogFooter className="border-t pt-3 flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={resetState} disabled={saving}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving || !selectedMemberId}
              className="gap-1.5"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              {saving ? "Saving..." : "Save Record"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {medSyncDiff && (
        <MedicationSyncDialog
          open={showMedSyncDialog}
          onOpenChange={(open) => {
            setShowMedSyncDialog(open);
            if (!open) {
              resetState();
              mutate("dashboard");
              mutate("members");
              mutate(`member-detail-${selectedMemberId}`);
            }
          }}
          diff={medSyncDiff}
          onApply={async (added, updated, removed) => {
            try {
              await applyMedicationSync(selectedMemberId, added, updated, removed);
              toast.success("Medications updated!");
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Failed to update medications");
              throw err; // re-throw so dialog stays open
            }
          }}
        />
      )}
    </>
  );
}
