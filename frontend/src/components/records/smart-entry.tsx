import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Camera, X, Loader2, Check, Pencil, Upload, Sparkles, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
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

type InputMode = "text" | "upload";
type Step = "input" | "confirm" | "saving";

/* ------------------------------------------------------------------ */
/*  SmartEntryBar — Dashboard inline widget                             */
/* ------------------------------------------------------------------ */

export function SmartEntryBar({ members }: SmartEntryBarProps) {
  const { mutate } = useSWRConfig();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedMemberId, setSelectedMemberId] = useState<string>("");
  const [mode, setMode] = useState<InputMode>("text");
  const [step, setStep] = useState<Step>("input");

  // Text input
  const [input, setInput] = useState("");
  const [parsed, setParsed] = useState<NLParseResponse | null>(null);

  // Upload input
  const [extracting, setExtracting] = useState(false);
  const [extractedData, setExtractedData] = useState<ExtractionResponse | null>(null);

  // Confirmation fields (shared by both flows)
  const [recordType, setRecordType] = useState<RecordType>("misc_record");
  const [recordDate, setRecordDate] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [prescriptionText, setPrescriptionText] = useState("");
  const [clinicalNotes, setClinicalNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const activeMembers = members.filter((m) => m.is_active);

  /* ── NL Text parse ── */
  const handleParse = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    try {
      const result = await parseNaturalLanguage(text);
      setParsed(result);
      if (result.member) setSelectedMemberId(result.member.id);
      setRecordType((result.record_type as RecordType) || "misc_record");
      setRecordDate(result.record_date || todayISO());
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
      const memberId = selectedMemberId;
      if (!memberId) {
        toast.error("Please select a family member first");
        return;
      }
      setExtracting(true);
      toast.info(`Processing ${file.name}...`);
      try {
        const response = await extractFromDocument(memberId, file);
        setExtractedData(response);
        setRecordType((response.extracted.record_type as RecordType) || "misc_record");
        setRecordDate(response.extracted.record_date || todayISO());
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
    [selectedMemberId]
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.[0]) processFile(e.target.files[0]);
    },
    [processFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer.files[0]) processFile(e.dataTransfer.files[0]);
    },
    [processFile]
  );

  /* ── Save ── */
  const handleSave = useCallback(async () => {
    if (!selectedMemberId) return;
    setSaving(true);
    try {
      await createRecord(
        selectedMemberId,
        {
          record_type: recordType,
          record_date: recordDate || todayISO(),
          record_time: extractedData?.extracted.record_time || nowTime(),
          clinical_data: clinicalNotes,
          diagnosis: diagnosis || null,
          prescription_text: prescriptionText || null,
          provider_id: null,
          next_review_date: extractedData?.extracted.next_review_date || null,
          tags: null,
        },
        extractedData?.staging_file_id || undefined,
        extractedData?.original_file_name || undefined
      );

      toast.success("Record saved!");
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
  }

  const _selectedMember = activeMembers.find((m) => m.id === selectedMemberId);

  return (
    <>
      <Card
        className="relative overflow-hidden transition-all duration-300 border shadow-none bg-card hover:bg-card/85 min-h-[148px]"
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={handleDrop}
      >
        <CardContent className="p-4 flex flex-col justify-between h-full min-h-[148px]">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/5 text-primary">
                {mode === "upload" ? (
                  <Sparkles className="h-4 w-4" />
                ) : (
                  <Activity className="h-4 w-4" />
                )}
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">
                  {mode === "upload" ? "AI Document Extractor" : "Quick Biometric Logger"}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {mode === "upload"
                    ? "Upload reports to auto-fill records"
                    : "Log vitals & glucose in natural language"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {/* Mode toggle */}
              <div className="flex items-center rounded-md border border-border/60 overflow-hidden">
                <button
                  onClick={() => setMode("text")}
                  className={`px-2 py-0.5 text-[10px] font-medium transition-colors ${mode === "text" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  Type
                </button>
                <button
                  onClick={() => setMode("upload")}
                  className={`px-2 py-0.5 text-[10px] font-medium transition-colors ${mode === "upload" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  Upload
                </button>
              </div>

              <MemberPicker
                members={members}
                value={selectedMemberId}
                onChange={setSelectedMemberId}
                size="sm"
              />
            </div>
          </div>

          {/* Input area */}
          <div className="flex-1 flex flex-col justify-end mt-3">
            {mode === "text" ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleParse();
                }}
                className="flex gap-2"
              >
                <Input
                  placeholder='Describe: "dad visited doctor, prescribed metformin 500mg" or "blood sugar 120"'
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  className="flex-1 text-xs"
                  disabled={extracting}
                />
                <Button type="submit" size="sm" disabled={!input.trim()}>
                  Parse
                </Button>
              </form>
            ) : (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  className="hidden"
                  onChange={handleFileChange}
                  disabled={extracting}
                />
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center justify-center border border-dashed border-border/60 hover:border-primary/45 rounded-lg py-4 px-2 cursor-pointer bg-muted/20 hover:bg-muted/40 transition-all select-none"
                >
                  {extracting ? (
                    <div className="flex flex-col items-center gap-1.5">
                      <Loader2 className="h-5 w-5 animate-spin text-primary" />
                      <p className="text-[10px] font-medium text-muted-foreground animate-pulse">
                        AI parsing document...
                      </p>
                    </div>
                  ) : (
                    <div className="text-center space-y-1">
                      <Upload className="h-5 w-5 mx-auto text-muted-foreground/60" />
                      <p className="text-[10px] font-medium text-foreground">
                        Drag & drop clinical report, PDF, or image
                      </p>
                      <p className="text-[9px] text-muted-foreground/60">
                        PDF, JPG, PNG up to 10MB
                      </p>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

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
            {/* Member */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Family Member</label>
              <MemberPicker
                members={members}
                value={selectedMemberId}
                onChange={setSelectedMemberId}
                size="md"
              />
            </div>

            {/* Type + Date */}
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

            {/* Diagnosis */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Diagnosis</label>
              <Input
                placeholder="e.g. Type 2 Diabetes"
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
                className="h-8 text-xs bg-background"
              />
            </div>

            {/* Prescriptions */}
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

            {/* Clinical Notes */}
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
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  SmartEntryFAB — Floating action button (replaces UniversalQuickEntry) */
/* ------------------------------------------------------------------ */

interface SmartEntryFABProps {
  members: { id: string; first_name: string; last_name: string; is_active: boolean }[];
}

export function SmartEntryFAB({ members }: SmartEntryFABProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("input");
  const [input, setInput] = useState("");
  const [parsed, setParsed] = useState<NLParseResponse | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [_memberPickerOpen, setMemberPickerOpen] = useState(false);
  const [_saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { mutate } = useSWRConfig();

  const activeMembers = members.filter((m) => m.is_active);

  const handleParse = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    try {
      const result = await parseNaturalLanguage(text);
      setParsed(result);
      if (result.member) setSelectedMemberId(result.member.id);
      setStep("confirm");
    } catch {
      toast.error("Couldn't parse that. Try rephrasing.");
    }
  }, [input]);

  const handleFileUpload = useCallback(
    async (file: File) => {
      const memberId = selectedMemberId || activeMembers[0]?.id;
      if (!memberId) {
        toast.error("Add a family member first");
        return;
      }
      setInput(`Uploading ${file.name}...`);
      try {
        const extraction = await extractFromDocument(memberId, file);
        const member = activeMembers.find((m) => m.id === memberId);
        setParsed({
          member: member
            ? {
                id: member.id,
                name: `${member.first_name} ${member.last_name}`,
                matched_by: "default",
              }
            : null,
          record_type: extraction.extracted.record_type ?? null,
          record_date: extraction.extracted.record_date ?? null,
          record_time: extraction.extracted.record_time ?? null,
          diagnosis: extraction.extracted.diagnosis ?? null,
          prescription_text: extraction.extracted.prescription_text ?? null,
          clinical_notes: extraction.extracted.clinical_data ?? null,
          next_review_date: extraction.extracted.next_review_date ?? null,
          confidence: extraction.confidence,
          preview_fields: [
            ...(extraction.extracted.record_type
              ? [
                  {
                    label: "Type",
                    value:
                      RECORD_TYPE_LABELS[
                        extraction.extracted.record_type as keyof typeof RECORD_TYPE_LABELS
                      ] || extraction.extracted.record_type,
                  },
                ]
              : []),
            ...(extraction.extracted.diagnosis
              ? [{ label: "Diagnosis", value: extraction.extracted.diagnosis }]
              : []),
            ...(extraction.extracted.prescription_text
              ? [{ label: "Rx", value: extraction.extracted.prescription_text.slice(0, 80) }]
              : []),
            ...(extraction.extracted.clinical_data
              ? [{ label: "Data", value: extraction.extracted.clinical_data.slice(0, 60) }]
              : []),
          ],
        });
        setSelectedMemberId(memberId);
        setStep("confirm");
      } catch {
        toast.error("Failed to extract data from document");
        setStep("input");
        setInput("");
      }
    },
    [selectedMemberId, activeMembers]
  );

  const handleSave = useCallback(async () => {
    if (!parsed || !selectedMemberId) return;
    setSaving(true);
    try {
      await createRecord(selectedMemberId, {
        record_type: (parsed.record_type || "misc_record") as RecordType,
        record_date: parsed.record_date || todayISO(),
        record_time: parsed.record_time || nowTime(),
        clinical_data: parsed.clinical_notes || "",
        diagnosis: parsed.diagnosis || null,
        prescription_text: parsed.prescription_text || null,
        provider_id: null,
        next_review_date: parsed.next_review_date || null,
        tags: null,
      });
      toast.success("Record saved!");
      resetFAB();
      mutate("dashboard");
    } catch {
      toast.error("Failed to save record");
      setStep("confirm");
    } finally {
      setSaving(false);
    }
  }, [parsed, selectedMemberId, mutate]);

  function resetFAB() {
    setOpen(false);
    setStep("input");
    setInput("");
    setParsed(null);
    setMemberPickerOpen(false);
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 transition-all hover:scale-105"
        aria-label="Quick add record"
      >
        <Plus className="h-6 w-6" />
      </button>
    );
  }

  const _selectedMember = activeMembers.find((m) => m.id === selectedMemberId);

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={resetFAB} />
      <div className="relative w-full max-w-lg bg-background rounded-t-2xl md:rounded-2xl shadow-xl border max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="text-sm font-semibold">Quick Add Record</h3>
          <button onClick={resetFAB} className="p-1 rounded-md hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {step === "input" && (
            <>
              <div className="flex gap-2">
                <Input
                  placeholder='Describe: "dad visited doctor, prescribed metformin 500mg"'
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && input.trim()) handleParse();
                  }}
                  className="flex-1 text-sm"
                  autoFocus
                />
                <Button size="sm" onClick={handleParse} disabled={!input.trim()}>
                  Parse
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-3.5 w-3.5" /> Upload document
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Camera className="h-3.5 w-3.5" /> Camera
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Type a description or upload a medical document. AI will extract the details.
              </p>
            </>
          )}

          {step === "confirm" && parsed && (
            <>
              <MemberPicker
                members={members}
                value={selectedMemberId ?? ""}
                onChange={setSelectedMemberId}
                size="md"
              />
              <div className="rounded-lg border p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={parsed.confidence === "high" ? "default" : "outline"}
                    className="text-xs"
                  >
                    {parsed.confidence} confidence
                  </Badge>
                  {parsed.record_type && (
                    <Badge variant="secondary" className="text-xs">
                      {RECORD_TYPE_LABELS[parsed.record_type as keyof typeof RECORD_TYPE_LABELS] ||
                        parsed.record_type}
                    </Badge>
                  )}
                </div>
                {parsed.preview_fields.length > 0 ? (
                  <div className="space-y-1">
                    {parsed.preview_fields.map((f, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <span className="text-muted-foreground text-xs min-w-[50px]">
                          {f.label}
                        </span>
                        <span className="text-foreground">{f.value}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No structured data extracted. You can edit in the full form.
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  className="flex-1 gap-1.5"
                  onClick={handleSave}
                  disabled={!selectedMemberId}
                >
                  <Check className="h-3.5 w-3.5" /> Save Record
                </Button>
                <Button
                  variant="outline"
                  className="gap-1.5"
                  onClick={() => {
                    if (selectedMemberId) {
                      resetFAB();
                      navigate(`/members/${selectedMemberId}/records/new`);
                    }
                  }}
                >
                  <Pencil className="h-3.5 w-3.5" /> Edit Full
                </Button>
              </div>
            </>
          )}

          {step === "saving" && (
            <div className="flex flex-col items-center py-6 gap-3">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Saving record...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
