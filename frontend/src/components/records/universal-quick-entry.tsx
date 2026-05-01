import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Camera, X, Loader2, Check, Pencil, ChevronDown, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { parseNaturalLanguage, createRecord, extractFromDocument } from "@/lib/api/records";
import type { NLParseResponse } from "@/lib/api/records";
import { setLastUsedMember, getLastUsedMember } from "@/lib/member-context";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { todayISO, nowTime } from "@/lib/quick-record";
import type { RecordType } from "@/lib/types/enums";
import { toast } from "sonner";

interface UniversalQuickEntryProps {
  members: { id: string; first_name: string; last_name: string; is_active: boolean }[];
}

type Step = "input" | "confirm" | "saving";

export function UniversalQuickEntry({ members }: UniversalQuickEntryProps) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("input");
  const [input, setInput] = useState("");
  const [parsed, setParsed] = useState<NLParseResponse | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [memberPickerOpen, setMemberPickerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeMembers = members.filter((m) => m.is_active);
  const lastUsed = getLastUsedMember();

  const handleParse = useCallback(async () => {
    const text = input.trim();
    if (!text) return;

    setStep("input"); // stays on input but shows loading
    try {
      const result = await parseNaturalLanguage(text);
      setParsed(result);

      // Resolve member
      if (result.member) {
        setSelectedMemberId(result.member.id);
      } else if (lastUsed) {
        const match = activeMembers.find((m) => m.id === lastUsed.id);
        if (match) setSelectedMemberId(match.id);
      }

      setStep("confirm");
    } catch {
      toast.error("Couldn't parse that. Try rephrasing.");
    }
  }, [input, lastUsed, activeMembers]);

  const handleFileUpload = useCallback(
    async (file: File) => {
      // Resolve member for extraction
      const memberId = selectedMemberId || lastUsed?.id || activeMembers[0]?.id;
      if (!memberId) {
        toast.error("Add a family member first");
        return;
      }

      setStep("input");
      setInput(`Uploading ${file.name}...`);

      try {
        const extraction = await extractFromDocument(memberId, file);
        // Build a pseudo-parsed response from extraction
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
                      RECORD_TYPE_LABELS[extraction.extracted.record_type] ||
                      extraction.extracted.record_type,
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
    [selectedMemberId, lastUsed, activeMembers]
  );

  const handleSave = useCallback(async () => {
    if (!parsed || !selectedMemberId) return;

    setStep("saving");
    try {
      const clinicalData = parsed.clinical_notes || "";
      const type = parsed.record_type || "misc_record";

      await createRecord(selectedMemberId, {
        record_type: type as RecordType,
        record_date: parsed.record_date || todayISO(),
        record_time: parsed.record_time || nowTime(),
        clinical_data: clinicalData,
        diagnosis: parsed.diagnosis || null,
        prescription_text: parsed.prescription_text || null,
        provider_id: null,
        next_review_date: parsed.next_review_date || null,
        tags: null,
      });

      const member = activeMembers.find((m) => m.id === selectedMemberId);
      if (member) setLastUsedMember(member.id, `${member.first_name} ${member.last_name}`);

      toast.success(`Record saved for ${member ? member.first_name : "member"}`);
      reset();
    } catch {
      toast.error("Failed to save record");
      setStep("confirm");
    }
  }, [parsed, selectedMemberId, activeMembers]);

  const handleEditFull = useCallback(() => {
    if (!selectedMemberId) return;
    setOpen(false);
    navigate(`/members/${selectedMemberId}/records/new`);
    reset();
  }, [selectedMemberId, navigate]);

  function reset() {
    setOpen(false);
    setStep("input");
    setInput("");
    setParsed(null);
    setMemberPickerOpen(false);
  }

  // FAB button to open
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

  const selectedMember = activeMembers.find((m) => m.id === selectedMemberId);

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={reset} />

      {/* Panel */}
      <div className="relative w-full max-w-lg bg-background rounded-t-2xl md:rounded-2xl shadow-xl border max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="text-sm font-semibold">Quick Add Record</h3>
          <button onClick={reset} className="p-1 rounded-md hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Step: Input */}
          {step === "input" && (
            <>
              {/* NL Input */}
              <div className="flex gap-2">
                <Input
                  placeholder='Describe the record: "dad visited doctor, prescribed metformin 500mg"'
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

              {/* File upload */}
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-3.5 w-3.5" />
                  Upload document
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Camera className="h-3.5 w-3.5" />
                  Camera
                </Button>
              </div>

              <p className="text-xs text-muted-foreground">
                Type a description or upload a medical document. AI will extract the details.
              </p>
            </>
          )}

          {/* Step: Confirm */}
          {step === "confirm" && parsed && (
            <>
              {/* Member selector */}
              <div className="relative">
                <button
                  onClick={() => setMemberPickerOpen(!memberPickerOpen)}
                  className="flex items-center gap-2 w-full rounded-lg border px-3 py-2 text-sm hover:bg-muted/50 transition-colors"
                >
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold shrink-0">
                    {selectedMember?.first_name?.[0] || "?"}
                  </div>
                  <span className="flex-1 text-left truncate">
                    {selectedMember
                      ? `${selectedMember.first_name} ${selectedMember.last_name}`
                      : "Select member"}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
                {memberPickerOpen && (
                  <div className="absolute top-full left-0 right-0 mt-1 rounded-lg border bg-popover shadow-lg z-10 max-h-40 overflow-y-auto">
                    {activeMembers.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => {
                          setSelectedMemberId(m.id);
                          setMemberPickerOpen(false);
                        }}
                        className={`flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-muted/50 transition-colors ${
                          m.id === selectedMemberId ? "bg-primary/10" : ""
                        }`}
                      >
                        {m.first_name} {m.last_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Parsed preview */}
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

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  className="flex-1 gap-1.5"
                  onClick={handleSave}
                  disabled={!selectedMemberId}
                >
                  <Check className="h-3.5 w-3.5" />
                  Save Record
                </Button>
                <Button variant="outline" className="gap-1.5" onClick={handleEditFull}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit Full
                </Button>
              </div>
            </>
          )}

          {/* Step: Saving */}
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
