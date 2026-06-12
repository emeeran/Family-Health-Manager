import { useState, useRef, useEffect, useMemo, useCallback, startTransition } from "react";
import { useActionState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Stepper } from "@/components/ui/stepper";
import { StepTypeSelection } from "./step-type-selection";
import { StepVisitDetails } from "./step-visit-details";
import { StepClinicalData } from "./step-clinical-data";
import { StepReview } from "./step-review";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MedicationSyncDialog } from "@/components/records/medication-sync-dialog";
import { useFileExtraction } from "@/components/records/use-file-extraction";
import {
  MEDICATION_SYNC_KEY,
  baseSchema,
  todayStr,
  timeAgo,
} from "@/components/records/record-form-utils";
import { getConfig } from "@/lib/record-type-configs";
import {
  serializeClinicalData,
  deserializeClinicalData,
  getDefaultCustomFields,
  getDefaultTableData,
} from "@/lib/clinical-data";
import { createProvider } from "@/lib/api/providers";
import { toDisplayDate, toISODate } from "@/lib/utils";
import { ArrowLeft, ArrowRight, Loader2, Plus } from "lucide-react";
import { useDirtyWarn } from "@/hooks/use-dirty-warn";
import type { FormValues } from "@/components/records/record-form-utils";
import type { RecordType } from "@/lib/types/enums";
import type { ProviderResponse, ProviderCreate } from "@/lib/types/provider";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import { Upload, FileText, CheckCircle2, Clock, X, AlertTriangle } from "lucide-react";

interface RecordFormProps {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  providers: ProviderResponse[];
  onProviderCreated?: (provider: ProviderResponse) => void;
  onSaveComplete?: () => void;
  record?: HealthRecordResponse;
  memberId?: string;
  defaultType?: RecordType;
  defaultProviderId?: string;
  defaultChiefComplaint?: string;
}

const STEPS = [
  { label: "Type & Files" },
  { label: "Visit Details" },
  { label: "Clinical Data" },
  { label: "Review" },
];

export function RecordFormWizard({
  action,
  providers: providersProp,
  onProviderCreated,
  onSaveComplete,
  record,
  memberId,
  defaultType,
  defaultProviderId,
  defaultChiefComplaint,
}: RecordFormProps) {
  const [currentStep, setCurrentStep] = useState(() => (defaultType ? 1 : 0));
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [customValues, setCustomValues] = useState<Record<string, string>>({});
  const [tableData, setTableData] = useState<Record<string, Record<string, string>[]>>({});
  const [notes, setNotes] = useState("");
  const [_extractedFields, setExtractedFields] = useState<Set<string>>(new Set());

  const [showMedPrompt, setShowMedPrompt] = useState(false);
  const [providerList, setProviderList] = useState<ProviderResponse[]>(providersProp);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProviderName, setNewProviderName] = useState("");
  const [newProviderSpeciality, setNewProviderSpeciality] = useState("");
  const [addingProvider, setAddingProvider] = useState(false);
  const [showMedSyncDialog, setShowMedSyncDialog] = useState(false);
  const [medSyncDiff, setMedSyncDiff] = useState<
    import("@/lib/types/health-record").MedicationDiffResponse | null
  >(null);
  const formRef = useRef<HTMLFormElement>(null);
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>(record?.tags ?? []);

  useEffect(() => setProviderList(providersProp), [providersProp]);

  const {
    register,
    setValue,
    watch,
    getValues,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(baseSchema),
    defaultValues: record
      ? {
          record_type: record.record_type,
          record_date: toDisplayDate(record.record_date),
          record_time: record.record_time ?? "",
          clinical_data: record.clinical_data,
          diagnosis: record.diagnosis ?? "",
          prescription_text: record.prescription_text ?? "",
          provider_id: record.provider_id ?? "",
          next_review_date: record.next_review_date ? toDisplayDate(record.next_review_date) : "",
        }
      : {
          record_type: defaultType || undefined,
          record_date: todayStr(),
          record_time: "",
          clinical_data: "",
          diagnosis: "",
          prescription_text: "",
          provider_id: defaultProviderId || "",
          next_review_date: "",
        },
  });

  const recordType = watch("record_type");
  const config = recordType ? getConfig(recordType) : null;

  // File extraction hook
  const {
    extracting,
    extractError,
    setExtractError,
    progress,
    uploadedFiles,
    stagingFileIds,
    fileInputRef,
    recentBatches,
    allAutoFillBatches,
    handleMultiFileExtract,
    handleFileDrop,
    handleTableAutoFill,
    handleRecentBatchClick,
    clearExtractionState,
    clearExtraction,
    removeBatch,
    refreshRecentBatches,
    transcription,
    setTranscription,
  } = useFileExtraction({
    memberId,
    record: record ?? null,
    recordType,
    providerList,
    form: { setValue, getValues, register, watch, reset, formState: { errors, isDirty } } as any,
    customValues,
    setCustomValues,
    tableData,
    setTableData,
    setNotes,
    setExtractedFields,
  });

  const handleAddProvider = useCallback(async () => {
    const name = newProviderName.trim();
    if (!name) return;
    setAddingProvider(true);
    try {
      const data: ProviderCreate = { name, speciality: newProviderSpeciality.trim() || undefined };
      const created = await createProvider(data);
      setProviderList((prev) => [...prev, created]);
      setValue("provider_id", created.id);
      onProviderCreated?.(created);
      setShowAddProvider(false);
      setNewProviderName("");
      setNewProviderSpeciality("");
    } catch {
      /* silently fail */
    } finally {
      setAddingProvider(false);
    }
  }, [newProviderName, newProviderSpeciality, setValue, onProviderCreated]);

  // When editing, deserialize clinical_data
  useEffect(() => {
    if (record && record.clinical_data) {
      const deserialized = deserializeClinicalData(record.clinical_data);
      if (deserialized.isStructured) {
        setCustomValues(deserialized.fields);
        setTableData(deserialized.tableData);
        setNotes(deserialized.notes);
        setValue("clinical_data", "");
      } else if (deserialized.fields.clinical_data) {
        setNotes(deserialized.fields.clinical_data);
        setCustomValues({});
        setTableData({});
      }
    }
  }, [record, setValue]);

  // Reset custom fields when record type changes
  const prevRecordTypeRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!record && recordType) {
      const cfg = getConfig(recordType);
      const defaults = getDefaultCustomFields(cfg);
      if (defaultChiefComplaint && "chief_complaint" in defaults) {
        defaults["chief_complaint"] = defaultChiefComplaint;
      }
      setCustomValues(defaults);
      if (prevRecordTypeRef.current !== undefined) {
        setTableData(getDefaultTableData(cfg));
      } else {
        setTableData((prev) => {
          const defaults = getDefaultTableData(cfg);
          const merged = { ...defaults };
          for (const key of Object.keys(defaults)) {
            if (prev[key] && prev[key].length > 0) merged[key] = prev[key];
          }
          return merged;
        });
      }
      setNotes("");
    }
    prevRecordTypeRef.current = recordType;
  }, [recordType, record, defaultChiefComplaint]);

  const clinicalDataRef = useRef<HTMLInputElement>(null);

  function handleCustomFieldChange(key: string, value: string) {
    setCustomValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleTableChange(tableKey: string, rows: Record<string, string>[]) {
    setTableData((prev) => ({ ...prev, [tableKey]: rows }));
  }

  const prescriptionRows = (tableData["prescriptions"] || []).filter((row) => row.medicine?.trim());
  const hasPrescriptions = prescriptionRows.length > 0;
  const isDoctorVisit = recordType === "doctor_visit";

  function serializeToHiddenField() {
    if (clinicalDataRef.current && config && recordType) {
      const serialized = serializeClinicalData(
        recordType,
        customValues,
        tableData,
        notes || undefined
      );
      clinicalDataRef.current.value = serialized;
    }
    const dateVal = getValues("record_date");
    if (dateVal) setValue("record_date", toISODate(dateVal));
    const reviewVal = getValues("next_review_date");
    if (reviewVal) setValue("next_review_date", toISODate(reviewVal));
  }

  const resetForm = useCallback(() => {
    reset({
      record_type: defaultType || undefined,
      record_date: todayStr(),
      record_time: "",
      clinical_data: "",
      diagnosis: "",
      prescription_text: "",
      provider_id: defaultProviderId || "",
      next_review_date: "",
    });
    clearExtractionState();
    setCustomValues({});
    setTableData({});
    setNotes("");
    setTags([]);
    setTagInput("");
    setCurrentStep(defaultType ? 1 : 0);
  }, [reset, defaultType, defaultProviderId, clearExtractionState]);

  function handleSubmit(e?: React.SyntheticEvent<HTMLFormElement>) {
    e?.preventDefault();
    if (isPending || !formRef.current) return;
    serializeToHiddenField();
    if (!record && recordType === "doctor_visit" && hasPrescriptions) {
      setShowMedPrompt(true);
      return;
    }
    const formData = new FormData(formRef.current);
    startTransition(() => {
      formAction(formData);
    });
  }

  function submitViaAction(updateMedications = true) {
    if (!formRef.current || isPending) return;
    serializeToHiddenField();
    const formData = new FormData(formRef.current);
    if (!updateMedications) {
      const clinicalStr = formData.get("clinical_data") as string;
      if (clinicalStr) {
        try {
          const parsed = JSON.parse(clinicalStr);
          if (parsed._type === "structured") {
            parsed[MEDICATION_SYNC_KEY] = false;
            formData.set("clinical_data", JSON.stringify(parsed));
          }
        } catch {
          /* not JSON */
        }
      }
    }
    startTransition(() => {
      formAction(formData);
    });
    setShowMedPrompt(false);
  }

  const tagsChanged = JSON.stringify(tags) !== JSON.stringify(record?.tags ?? []);
  useDirtyWarn(isDirty || tagsChanged || !!recordType, isPending);

  // After successful save, check for medication sync
  const prevPendingRef = useRef(false);
  useEffect(() => {
    if (prevPendingRef.current && !isPending && state) {
      const result = state as Record<string, unknown>;
      if (result.success && result.prescriptions && memberId) {
        const rx = result.prescriptions as Record<string, string>[];
        import("@/lib/api/members").then(({ computeMedicationDiff }) => {
          computeMedicationDiff(
            memberId,
            rx,
            (result.record as Record<string, unknown>)?.id as string
          )
            .then((diff) => {
              const total = diff.added.length + diff.updated.length + diff.removed.length;
              if (total > 0) {
                setMedSyncDiff(diff);
                setShowMedSyncDialog(true);
              } else {
                resetForm();
                onSaveComplete?.();
              }
            })
            .catch(() => {
              resetForm();
              onSaveComplete?.();
            });
        });
      } else if (result.success) {
        resetForm();
        onSaveComplete?.();
      }
    }
    prevPendingRef.current = isPending;
  }, [isPending, state, memberId, onSaveComplete, resetForm]);

  // Get provider name for review step
  const selectedProviderId = watch("provider_id");
  const providerName = useMemo(() => {
    if (!selectedProviderId) return null;
    return providerList.find((p) => p.id === selectedProviderId)?.name ?? null;
  }, [selectedProviderId, providerList]);

  // Completed steps for stepper
  const completedSteps = useMemo(() => {
    const completed: number[] = [];
    if (currentStep > 0) {
      // Step 0 is "completed" if we have a type and date
      if (recordType) completed.push(0);
    }
    return completed;
  }, [currentStep, recordType]);

  // Upload section (injected into Step 1)
  const uploadSection = memberId && !record && (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Upload & Extract
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={() => fileInputRef.current?.click()}
          disabled={extracting}
        >
          <Plus className="h-3 w-3 mr-1" /> Add Files
        </Button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,image/jpeg,image/png"
        capture="environment"
        multiple
        disabled={extracting}
        className="hidden"
        onChange={() => {
          if (fileInputRef.current?.files?.length) handleMultiFileExtract();
        }}
      />

      <div
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragOver(true);
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsDragOver(false);
          const files = Array.from(e.dataTransfer.files);
          if (files.length) handleFileDrop(files);
        }}
        className={`flex items-center justify-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm transition-all cursor-pointer ${isDragOver ? "border-primary bg-primary/10" : "border-muted-foreground/20 hover:border-primary/40 hover:bg-primary/5"}`}
      >
        <Upload className="h-4 w-4 text-muted-foreground/50" />
        <span className="text-muted-foreground">Drop or click to upload PDF, JPEG, PNG</span>
      </div>

      {extracting && (
        <div className="rounded-lg border bg-card p-3 space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium">{progress.step}</span>
            <span className="text-muted-foreground tabular-nums">{progress.pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progress.pct}%` }}
            />
          </div>
          {progress.substeps.length > 0 && (
            <div className="space-y-1 pt-1">
              {progress.substeps.map((sub, idx) => {
                const isDone = progress.done.includes(sub);
                const isCurrent = !isDone && progress.done.length === idx;
                return (
                  <div key={sub} className="flex items-center gap-2 text-xs">
                    {isDone ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                    ) : isCurrent ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />
                    ) : (
                      <div className="h-3.5 w-3.5 rounded-full border border-muted-foreground/30 shrink-0" />
                    )}
                    <span
                      className={
                        isDone
                          ? "text-muted-foreground line-through"
                          : isCurrent
                            ? "font-medium text-foreground"
                            : "text-muted-foreground/60"
                      }
                    >
                      {sub}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {uploadedFiles.length > 0 && !extracting && (
        <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-950">
          <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-medium text-green-700 dark:text-green-400">
              Extracted {uploadedFiles.length} file{uploadedFiles.length !== 1 ? "s" : ""} — review
              data below
            </p>
            {uploadedFiles.map((f) => (
              <p
                key={f.stagingId}
                className="text-[11px] text-green-600/70 dark:text-green-500 flex items-center gap-1 mt-0.5"
              >
                <FileText className="h-3 w-3" /> {f.name}
              </p>
            ))}
          </div>
        </div>
      )}

      {transcription && uploadedFiles.length > 0 && !extracting && (
        <details className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-800 dark:bg-amber-950/50">
          <summary className="text-xs font-medium text-amber-800 dark:text-amber-400 cursor-pointer flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            AI Transcription — review and edit what was read from the document
          </summary>
          <textarea
            value={transcription}
            onChange={(e) => setTranscription(e.target.value)}
            className="mt-2 w-full text-xs text-amber-900 dark:text-amber-300 font-mono leading-relaxed min-h-[80px] max-h-[200px] bg-white/50 dark:bg-black/20 border border-amber-200 dark:border-amber-700 rounded-md p-2 focus:outline-none focus:ring-1 focus:ring-amber-400"
            rows={4}
          />
        </details>
      )}

      {recentBatches.length > 0 && uploadedFiles.length === 0 && !extracting && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Recent Files
            </p>
            <button
              type="button"
              onClick={() => {
                if (memberId) {
                  clearExtraction(memberId);
                  refreshRecentBatches();
                }
              }}
              className="text-xs text-muted-foreground hover:text-destructive transition-colors"
            >
              Clear all
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {recentBatches.map((batch) => {
              const parts: string[] = [];
              if (batch.prescriptions.length) parts.push(`${batch.prescriptions.length} rx`);
              if (batch.labTests.length) parts.push(`${batch.labTests.length} labs`);
              const summary = parts.join(", ") || "no data";
              return (
                <div
                  key={batch.id}
                  className="group relative inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors"
                >
                  <button
                    type="button"
                    onClick={() => handleRecentBatchClick(batch.id)}
                    className="inline-flex items-center gap-1.5"
                  >
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium max-w-[140px] truncate">{batch.fileName}</span>
                    <span className="text-muted-foreground">{summary}</span>
                    <span className="text-xs text-muted-foreground/60 flex items-center gap-0.5">
                      <Clock className="h-2.5 w-2.5" />
                      {timeAgo(batch.timestamp)}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (memberId) {
                        removeBatch(memberId, batch.id);
                        refreshRecentBatches();
                      }
                    }}
                    className="ml-0.5 rounded-sm p-0.5 text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-colors"
                    title="Remove"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {extractError && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
          <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-destructive">{extractError}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setExtractError(null);
              fileInputRef.current?.click();
            }}
            className="shrink-0 text-sm font-semibold text-primary hover:underline underline-offset-2"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );

  return (
    <form ref={formRef} action={formAction} onSubmit={handleSubmit} className="space-y-4 max-w-3xl">
      {/* Error banner */}
      {Boolean(
        state && typeof state === "object" && "error" in (state as Record<string, unknown>)
      ) && (
        <div
          role="alert"
          className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {String((state as Record<string, unknown>).error ?? "Unknown error")}
        </div>
      )}

      {/* Hidden fields */}
      <input
        ref={clinicalDataRef}
        type="hidden"
        name="clinical_data"
        defaultValue={record?.clinical_data || ""}
      />
      <input type="hidden" name="record_time" value="" />
      {stagingFileIds.length > 0 && (
        <input type="hidden" name="staging_file_ids" value={stagingFileIds.join(",")} />
      )}
      {uploadedFiles.length > 0 && (
        <input
          type="hidden"
          name="original_file_names"
          value={uploadedFiles.map((f) => f.name).join(",")}
        />
      )}

      {/* Stepper */}
      <Stepper
        steps={STEPS}
        currentStep={currentStep}
        completedSteps={completedSteps}
        onStepClick={setCurrentStep}
        size="sm"
      />

      {/* Step content */}
      <div key={currentStep} className="animate-fade-in-up">
        {currentStep === 0 && (
          <StepTypeSelection
            recordType={recordType}
            onRecordTypeChange={(type) => setValue("record_type", type)}
            register={register}
            errors={errors}
            uploadSection={uploadSection}
          />
        )}

        {currentStep === 1 && (
          <StepVisitDetails
            providers={providerList}
            register={register}
            isDoctorVisit={isDoctorVisit}
            showProviderSelect={!!config?.schemaFields.provider_id}
            onAddProvider={() => setShowAddProvider(true)}
            chiefComplaint={customValues["chief_complaint"] || ""}
            onChiefComplaintChange={(v) => handleCustomFieldChange("chief_complaint", v)}
            diagnosis={getValues("diagnosis") ?? ""}
            nextReviewDate={getValues("next_review_date") ?? ""}
            notes={customValues["notes"] || ""}
            onNotesChange={(v) => handleCustomFieldChange("notes", v)}
            tags={tags}
            onTagsChange={setTags}
            tagInput={tagInput}
            onTagInputChange={setTagInput}
            providerLabel={isDoctorVisit ? "Consultant" : "Provider"}
          />
        )}

        {currentStep === 2 && (
          <StepClinicalData
            recordType={recordType}
            config={config}
            customValues={customValues}
            onCustomFieldChange={handleCustomFieldChange}
            tableData={tableData}
            onTableChange={handleTableChange}
            onAutoFillBatch={handleTableAutoFill}
            autoFillBatches={allAutoFillBatches}
            notes={notes}
            onNotesChange={setNotes}
            isDoctorVisit={isDoctorVisit}
            clinicalDataRef={clinicalDataRef}
            register={register}
          />
        )}

        {currentStep === 3 && (
          <StepReview
            recordType={recordType}
            recordDate={getValues("record_date") ?? ""}
            recordTime={getValues("record_time") || undefined}
            providerName={providerName}
            chiefComplaint={isDoctorVisit ? customValues["chief_complaint"] : undefined}
            diagnosis={getValues("diagnosis") ?? null}
            customValues={customValues}
            tableData={tableData}
            notes={notes}
            tags={tags}
            uploadedFiles={uploadedFiles}
            config={config}
            isDoctorVisit={isDoctorVisit}
            isPending={isPending}
            isEditing={!!record}
            onSubmit={() => handleSubmit()}
            onReset={resetForm}
          />
        )}
      </div>

      {/* Back/Next footer (not on step 0 or 3) */}
      {currentStep < 3 && (
        <div className="flex justify-between pt-2">
          {currentStep > 0 ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCurrentStep(currentStep - 1)}
            >
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Button>
          ) : (
            <div />
          )}
          <Button
            type="button"
            size="sm"
            onClick={() => setCurrentStep(currentStep + 1)}
            disabled={currentStep === 0 && !recordType}
          >
            Next
            <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      )}

      {/* Add Provider dialog */}
      <Dialog open={showAddProvider} onOpenChange={setShowAddProvider}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Add Provider</DialogTitle>
            <DialogDescription>Create a new provider to link to this record.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            <div className="space-y-1">
              <Label className="text-xs">Name</Label>
              <Input
                placeholder="e.g. Dr. Jane Smith"
                className="h-9"
                value={newProviderName}
                onChange={(e) => setNewProviderName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddProvider();
                  }
                }}
                autoFocus
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Speciality</Label>
              <Input
                placeholder="e.g. Cardiology"
                className="h-9"
                value={newProviderSpeciality}
                onChange={(e) => setNewProviderSpeciality(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddProvider();
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowAddProvider(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleAddProvider}
              disabled={!newProviderName.trim() || addingProvider}
            >
              {addingProvider && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
              {addingProvider ? "Adding..." : "Add Provider"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Medication update confirmation */}
      <Dialog open={showMedPrompt} onOpenChange={setShowMedPrompt}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Update Currently Taking Medications?</DialogTitle>
            <DialogDescription>
              This record contains {prescriptionRows.length} prescription
              {prescriptionRows.length !== 1 ? "s" : ""}. After saving, the &quot;Currently
              Taking&quot; list will be automatically updated — older prescriptions for the same
              medicines will be replaced with these latest ones.
            </DialogDescription>
          </DialogHeader>
          <div className="my-2 rounded-lg border p-3 max-h-[200px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="pb-1 text-left text-xs font-semibold text-muted-foreground uppercase">
                    Type
                  </th>
                  <th className="pb-1 px-2 text-left text-xs font-semibold text-muted-foreground uppercase">
                    Medicine
                  </th>
                  <th className="pb-1 px-2 text-left text-xs font-semibold text-muted-foreground uppercase">
                    Dose
                  </th>
                  <th className="pb-1 px-2 text-left text-xs font-semibold text-muted-foreground uppercase">
                    Timing
                  </th>
                </tr>
              </thead>
              <tbody>
                {prescriptionRows.map((rx, i) => (
                  <tr key={i} className="border-b border-border/30">
                    <td className="py-1 text-xs">{rx.type || "—"}</td>
                    <td className="py-1 px-2 text-xs font-medium">{rx.medicine}</td>
                    <td className="py-1 px-2 text-xs">{rx.dosage || "—"}</td>
                    <td className="py-1 px-2 text-xs text-muted-foreground">
                      {rx.timing ? rx.timing.replace(/_/g, " ") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setShowMedPrompt(false)}>
              Cancel
            </Button>
            <Button variant="outline" size="sm" onClick={() => submitViaAction(false)}>
              Save Only
            </Button>
            <Button size="sm" onClick={() => submitViaAction(true)}>
              Save & Update Medications
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Medication sync dialog */}
      {medSyncDiff && (
        <MedicationSyncDialog
          open={showMedSyncDialog}
          onOpenChange={(open) => {
            setShowMedSyncDialog(open);
            if (!open) onSaveComplete?.();
          }}
          diff={medSyncDiff}
          onApply={async (added, updated, removed) => {
            if (!memberId) return;
            const { applyMedicationSync } = await import("@/lib/api/members");
            await applyMedicationSync(memberId, added, updated, removed);
          }}
        />
      )}
    </form>
  );
}
