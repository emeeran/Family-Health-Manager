/**
 * Shared stateful core for the record forms (classic RecordForm + RecordFormWizard).
 *
 * Both renderers used to copy-paste ~90% of this logic (form state, file/NL
 * extraction wiring, provider management, type-change reset, validation, submit,
 * and the post-save medication-sync flow). It now lives here once. The renderers
 * differ only in layout (single page vs. wizard steps), so they stay separate and
 * consume this hook.
 */
import { useState, useRef, useEffect, useMemo, useCallback, startTransition } from "react";
import { useActionState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { getConfig, getTables } from "@/lib/record-type-configs";
import { todayISO } from "@/lib/quick-record";
import {
  serializeClinicalData,
  deserializeClinicalData,
  getDefaultCustomFields,
  getDefaultTableData,
} from "@/lib/clinical-data";
import { useFileExtraction } from "./use-file-extraction";
import { useNLExtraction } from "./use-nl-extraction";
import { MEDICATION_SYNC_KEY, baseSchema } from "./record-form-utils";
import type { FormValues } from "./record-form-utils";
import type { RecordType } from "@/lib/types/enums";
import type { ProviderResponse, ProviderCreate } from "@/lib/types/provider";
import type { HealthRecordResponse, MedicationDiffResponse } from "@/lib/types/health-record";
import { createProvider } from "@/lib/api/providers";
import { consumePendingEntry } from "@/lib/pending-entry";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export interface UseRecordFormStateArgs {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  providers: ProviderResponse[];
  onProviderCreated?: (provider: ProviderResponse) => void;
  onSaveComplete?: () => void;
  record?: HealthRecordResponse;
  memberId?: string;
  defaultType?: RecordType;
  defaultProviderId?: string;
  defaultChiefComplaint?: string;
  /** Pre-filled NL text (e.g. from ?nl=) — auto-parsed on mount. Wizard only. */
  initialNLText?: string;
  /** Called after the form resets (wizard uses it to return to the first step). */
  onAfterReset?: () => void;
  /** Called when required-field validation fails (wizard uses it to jump to the step). */
  onValidationError?: (errors: Record<string, string>) => void;
}

export function useRecordFormState({
  action,
  providers: providersProp,
  onProviderCreated,
  onSaveComplete,
  record,
  memberId,
  defaultType,
  defaultProviderId,
  defaultChiefComplaint,
  initialNLText,
  onAfterReset,
  onValidationError,
}: UseRecordFormStateArgs) {
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);
  const navigate = useNavigate();

  const [customValues, setCustomValues] = useState<Record<string, string>>({});
  const [tableData, setTableData] = useState<Record<string, Record<string, string>[]>>({});
  const [notes, setNotes] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [_extractedFields, setExtractedFields] = useState<Set<string>>(new Set());

  const [showMedPrompt, setShowMedPrompt] = useState(false);
  const [providerList, setProviderList] = useState<ProviderResponse[]>(providersProp);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProviderName, setNewProviderName] = useState("");
  const [newProviderSpeciality, setNewProviderSpeciality] = useState("");
  const [addingProvider, setAddingProvider] = useState(false);
  const [providerError, setProviderError] = useState("");
  const [showMedSyncDialog, setShowMedSyncDialog] = useState(false);
  const [medSyncDiff, setMedSyncDiff] = useState<MedicationDiffResponse | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const clinicalDataRef = useRef<HTMLInputElement>(null);
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>(record?.tags ?? []);

  useEffect(() => setProviderList(providersProp), [providersProp]);

  const form = useForm<FormValues>({
    resolver: zodResolver(baseSchema),
    defaultValues: record
      ? {
          record_type: record.record_type,
          record_date: record.record_date,
          record_time: record.record_time ?? "",
          clinical_data: record.clinical_data,
          diagnosis: record.diagnosis ?? "",
          prescription_text: record.prescription_text ?? "",
          provider_id: record.provider_id ?? "",
          next_review_date: record.next_review_date ?? "",
        }
      : {
          record_type: defaultType || undefined,
          record_date: todayISO(),
          record_time: "",
          clinical_data: "",
          diagnosis: "",
          prescription_text: "",
          provider_id: defaultProviderId || "",
          next_review_date: "",
        },
  });
  const {
    register,
    setValue,
    watch,
    getValues,
    reset,
    formState: { errors, isDirty },
  } = form;

  const recordType = watch("record_type");
  const config = recordType ? getConfig(recordType) : null;
  const tables = useMemo(() => (recordType ? getTables(getConfig(recordType)) : []), [recordType]);
  const isDoctorVisit = recordType === "doctor_visit";

  // ── File extraction ──
  const extraction = useFileExtraction({
    memberId,
    record: record ?? null,
    recordType,
    providerList,
    form: { ...form, formState: { errors, isDirty } } as any,
    customValues,
    setCustomValues,
    tableData,
    setTableData,
    setNotes,
    setExtractedFields,
  });

  // ── Natural-language extraction ──
  const nl = useNLExtraction({
    recordType,
    providerList,
    form: { setValue, getValues },
    setCustomValues,
    setTableData,
    setExtractedFields,
  });

  const handleAddProvider = useCallback(async () => {
    const name = newProviderName.trim();
    if (!name) return;
    setAddingProvider(true);
    setProviderError("");
    try {
      const data: ProviderCreate = { name, speciality: newProviderSpeciality.trim() || undefined };
      const created = await createProvider(data);
      setProviderList((prev) => [...prev, created]);
      setValue("provider_id", created.id);
      onProviderCreated?.(created);
      setShowAddProvider(false);
      setNewProviderName("");
      setNewProviderSpeciality("");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to add provider";
      setProviderError(msg);
      toast.error(msg);
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

  // Reset custom fields when record type changes. Manual switches start clean;
  // programmatic changes (extraction / NL merge) preserve AI-filled values.
  const prevRecordTypeRef = useRef<string | undefined>(undefined);
  const userPickedTypeRef = useRef(false);
  useEffect(() => {
    if (!record && recordType) {
      const cfg = getConfig(recordType);
      const baseDefaults = getDefaultCustomFields(cfg);
      if (defaultChiefComplaint && "chief_complaint" in baseDefaults) {
        baseDefaults["chief_complaint"] = defaultChiefComplaint;
      }
      if (userPickedTypeRef.current) {
        setCustomValues(baseDefaults);
        setTableData(getDefaultTableData(cfg));
      } else {
        setCustomValues((prev) => {
          const merged = { ...baseDefaults };
          for (const [k, v] of Object.entries(prev)) {
            if (v !== undefined && v !== "") merged[k] = v;
          }
          return merged;
        });
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
      setFieldErrors({});
    }
    userPickedTypeRef.current = false;
    prevRecordTypeRef.current = recordType;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordType, record]);

  // Consume launcher input on mount (wizard NL auto-parse / handed-off file).
  useEffect(() => {
    if (record) return;
    const pending = consumePendingEntry();
    const text = initialNLText || pending?.text;
    if (text && text.trim()) {
      void nl.parseText(text);
    } else if (pending?.file) {
      extraction.handleFileDrop([pending.file]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleCustomFieldChange(key: string, value: string) {
    setCustomValues((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function handleTableChange(tableKey: string, rows: Record<string, string>[]) {
    setTableData((prev) => ({ ...prev, [tableKey]: rows }));
  }

  const prescriptionRows = (tableData["prescriptions"] || []).filter((row) => row.medicine?.trim());
  const hasPrescriptions = prescriptionRows.length > 0;

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
  }

  const resetForm = useCallback(() => {
    reset({
      record_type: defaultType || undefined,
      record_date: todayISO(),
      record_time: "",
      clinical_data: "",
      diagnosis: "",
      prescription_text: "",
      provider_id: defaultProviderId || "",
      next_review_date: "",
    });
    extraction.clearExtractionState();
    setCustomValues({});
    setTableData({});
    setNotes("");
    setTags([]);
    setTagInput("");
    setFieldErrors({});
    onAfterReset?.();
  }, [reset, defaultType, defaultProviderId, extraction, onAfterReset]);

  function validateRequiredFields(): Record<string, string> {
    const errs: Record<string, string> = {};
    if (config) {
      for (const f of config.customFields) {
        if (f.required && !(customValues[f.key] || "").trim()) {
          errs[f.key] = `${f.label} is required`;
        }
      }
    }
    return errs;
  }

  /** Validate, then either submit or open the med-update prompt for new doctor visits. */
  function handleSubmit(e?: React.SyntheticEvent<HTMLFormElement>) {
    e?.preventDefault();
    if (isPending || !formRef.current) return;
    const errs = validateRequiredFields();
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      toast.error("Please fill in the required fields.");
      onValidationError?.(errs);
      return;
    }
    setFieldErrors({});
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

  const hasCustomFields = config && config.customFields.length > 0;
  const hasTables = tables.length > 0;
  const hasStructuredContent = hasCustomFields || hasTables;

  const typeSpecificConfig = useMemo(() => {
    if (!config) return null;
    if (isDoctorVisit) {
      const hiddenKeys = new Set(["chief_complaint", "notes"]);
      return {
        ...config,
        customFields: config.customFields.filter((f) => !hiddenKeys.has(f.key)),
        tables: undefined,
        tableRows: undefined,
      };
    }
    return config;
  }, [config, isDoctorVisit]);

  // After successful save, check for medication sync
  const prevPendingRef = useRef(false);
  useEffect(() => {
    if (prevPendingRef.current && !isPending && state) {
      const result = state as Record<string, unknown>;
      if (result.success) {
        const recordId = (result.record as Record<string, unknown> | undefined)?.id as
          | string
          | undefined;
        toast.success("Record created", {
          action: recordId
            ? { label: "View", onClick: () => navigate(`/people/${memberId}/records/${recordId}`) }
            : undefined,
        });
        if (result.prescriptions && memberId) {
          const rx = result.prescriptions as Record<string, string>[];
          import("@/lib/api/members").then(({ computeMedicationDiff }) => {
            computeMedicationDiff(memberId, rx, recordId as string)
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
        } else {
          resetForm();
          onSaveComplete?.();
        }
      }
    }
    prevPendingRef.current = isPending;
  }, [isPending, state, memberId, onSaveComplete, resetForm, navigate]);

  return {
    // form
    form,
    register,
    setValue,
    watch,
    getValues,
    reset,
    errors,
    isDirty,
    formAction,
    formRef,
    clinicalDataRef,
    // record state
    state,
    isPending,
    recordType,
    config,
    tables,
    isDoctorVisit,
    hasCustomFields,
    hasTables,
    hasStructuredContent,
    typeSpecificConfig,
    // structured content
    customValues,
    setCustomValues,
    tableData,
    notes,
    setNotes,
    fieldErrors,
    tags,
    setTags,
    tagInput,
    setTagInput,
    handleCustomFieldChange,
    handleTableChange,
    // submit flow
    handleSubmit,
    submitViaAction,
    resetForm,
    validateRequiredFields,
    serializeToHiddenField,
    // med prompt / sync
    showMedPrompt,
    setShowMedPrompt,
    prescriptionRows,
    hasPrescriptions,
    medSyncDiff,
    showMedSyncDialog,
    setShowMedSyncDialog,
    // provider
    providerList,
    showAddProvider,
    setShowAddProvider,
    newProviderName,
    setNewProviderName,
    newProviderSpeciality,
    setNewProviderSpeciality,
    addingProvider,
    providerError,
    setProviderError,
    handleAddProvider,
    // type-change marker (renderers set this before a manual type change)
    userPickedTypeRef,
    // extraction + NL
    extraction,
    nl,
  };
}
