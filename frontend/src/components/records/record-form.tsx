import { useState, useRef, useEffect, useMemo, useCallback, startTransition } from "react";
import { useActionState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
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
import { Badge } from "@/components/ui/badge";
import { RECORD_TYPE_LABELS, ALLOWED_MIME_TYPES, MAX_FILE_SIZE } from "@/lib/constants";
import { toDisplayDate, toISODate } from "@/lib/utils";
import { getConfig, getTables } from "@/lib/record-type-configs";
import {
  serializeClinicalData,
  deserializeClinicalData,
  getDefaultCustomFields,
  getDefaultTableData,
} from "@/lib/clinical-data";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  saveExtraction,
  consumeBatch,
  loadExtraction,
  getBatchesForType,
  removeBatch,
  clearExtraction,
} from "@/lib/extraction-store";

import { TypeSpecificFields } from "./type-specific-fields";
import { DynamicTable } from "./dynamic-table";
import { MedicationSyncDialog } from "./medication-sync-dialog";
import type { RecordType } from "@/lib/types/enums";
import type { ProviderResponse, ProviderCreate } from "@/lib/types/provider";
import type { HealthRecordResponse, ExtractionResponse } from "@/lib/types/health-record";
import { createProvider } from "@/lib/api/providers";
import {
  Loader2,
  Upload,
  FileText,
  CheckCircle2,
  Clock,
  Plus,
  X,
  RotateCcw,
  AlertTriangle,
} from "lucide-react";
import { useDirtyWarn } from "@/hooks/use-dirty-warn";

const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : "/api/v1";

// Static — computed once at module level, never changes
const RECORD_TYPE_OPTIONS = Object.entries(RECORD_TYPE_LABELS) as [RecordType, string][];

const VALID_RECORD_TYPES = new Set<string>([
  "doctor_visit",
  "lab_report",
  "rx_eyeglass",
  "blood_glucose",
  "misc_record",
  "vitals",
  "parkinsons_log",
]);

const EXTRACT_TIMEOUT = 300_000; // 5 min — local models can be slow on complex multi-page PDFs
const MEDICATION_SYNC_KEY = "_medication_sync";
const VALID_MED_TYPES = new Set(["Tab", "Cap", "Inj", "Syp", "Cream", "Drops", "Inhaler", "Other"]);
const VALID_TIMINGS = new Set([
  "before_food",
  "after_food",
  "with_food",
  "empty_stomach",
  "bedtime",
  "sos",
  "stat",
]);

/** Normalize various date formats to YYYY-MM-DD, or return null */
function normalizeDate(val: unknown): string | null {
  if (!val || typeof val !== "string") return null;
  const s = val.trim();
  // Already YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  // DD/MM/YYYY or DD-MM-YYYY
  const dmy = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
  // Try native parse as last resort
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return null;
}

/** Normalize time to HH:MM, handling HH:MM:SS from backend */
function normalizeTime(val: unknown): string | null {
  if (!val || typeof val !== "string") return null;
  const s = val.trim();
  const m = s.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return null;
  const h = Number(m[1]);
  const mins = Number(m[2]);
  if (h < 0 || h > 23 || mins < 0 || mins > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

function sanitizeText(val: unknown, maxLen = 500): string | null {
  if (!val || typeof val !== "string") return null;
  const trimmed = val.trim();
  if (!trimmed) return null;
  return trimmed.length > maxLen ? trimmed.slice(0, maxLen) : trimmed;
}

function validatePrescriptionRow(row: unknown): Record<string, string> | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  const medicine = sanitizeText(r.medicine, 200);
  if (!medicine) return null;
  return {
    type: VALID_MED_TYPES.has(r.type as string) ? (r.type as string) : "Tab",
    medicine,
    dosage: sanitizeText(r.dosage, 50) || "",
    duration: sanitizeText(r.duration, 50) || "",
    timing: VALID_TIMINGS.has(r.timing as string) ? (r.timing as string) : "",
    note: sanitizeText(r.note, 200) || "",
  };
}

function validateLabTestRow(row: unknown): Record<string, string> | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  const test_name = sanitizeText(r.test_name, 200);
  if (!test_name) return null;
  return {
    test_name,
    result: sanitizeText(r.result, 100) || "",
    ref_value: sanitizeText(r.ref_value, 100) || "",
    note: sanitizeText(r.note, 200) || "",
  };
}

const baseSchema = z.object({
  record_type: z.enum([
    "doctor_visit",
    "lab_report",
    "rx_eyeglass",
    "blood_glucose",
    "hba1c",
    "misc_record",
    "vitals",
    "parkinsons_log",
  ] as const),
  record_date: z.string().min(1, "Record date is required"),
  record_time: z.string().optional(),
  clinical_data: z.string().optional(),
  diagnosis: z.string().optional(),
  prescription_text: z.string().optional(),
  provider_id: z.string().optional(),
  next_review_date: z.string().optional(),
});

type FormValues = z.infer<typeof baseSchema>;

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

interface UploadedFile {
  name: string;
  stagingId: string;
}

function todayStr() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}-${mm}-${d.getFullYear()}`;
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export function RecordForm({
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
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);
  const [stagingFileIds, setStagingFileIds] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [progress, setProgress] = useState({
    step: "",
    pct: 0,
    substeps: [] as string[],
    done: [] as string[],
  });
  const [_extractedFields, setExtractedFields] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Dynamic field state — keyed by table key
  const [customValues, setCustomValues] = useState<Record<string, string>>({});
  const [tableData, setTableData] = useState<Record<string, Record<string, string>[]>>({});
  const [notes, setNotes] = useState("");

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

  // Sync local provider list when parent data changes
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
  const tables = useMemo(() => (config ? getTables(config) : []), [config]);

  const handleAddProvider = useCallback(async () => {
    const name = newProviderName.trim();
    if (!name) return;
    setAddingProvider(true);
    try {
      const data: ProviderCreate = {
        name,
        speciality: newProviderSpeciality.trim() || undefined,
      };
      const created = await createProvider(data);
      setProviderList((prev) => [...prev, created]);
      setValue("provider_id", created.id);
      onProviderCreated?.(created);
      setShowAddProvider(false);
      setNewProviderName("");
      setNewProviderSpeciality("");
    } catch {
      // Silently fail — user can retry
    } finally {
      setAddingProvider(false);
    }
  }, [newProviderName, newProviderSpeciality, setValue, onProviderCreated]);

  // When editing, deserialize clinical_data into structured fields
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

  // Track if this is the initial type selection (not a user change)
  const prevRecordTypeRef = useRef<string | undefined>(undefined);

  // Reset custom fields when record type changes (new records only)
  useEffect(() => {
    if (!record && recordType) {
      const cfg = getConfig(recordType);
      const defaults = getDefaultCustomFields(cfg);
      // Re-apply any pending extracted fields on top of defaults
      if (pendingExtractedFields.current) {
        Object.assign(defaults, pendingExtractedFields.current);
        pendingExtractedFields.current = null;
      }
      // Apply pre-consultation chief complaint if provided
      if (defaultChiefComplaint && "chief_complaint" in defaults) {
        defaults["chief_complaint"] = defaultChiefComplaint;
      }
      setCustomValues(defaults);
      // Only reset table data on explicit user change, not first selection
      if (prevRecordTypeRef.current !== undefined) {
        setTableData(getDefaultTableData(cfg));
      } else {
        // First selection — ensure table keys exist but don't wipe existing data
        setTableData((prev) => {
          const defaults = getDefaultTableData(cfg);
          const merged = { ...defaults };
          for (const key of Object.keys(defaults)) {
            if (prev[key] && prev[key].length > 0) {
              merged[key] = prev[key];
            }
          }
          return merged;
        });
      }
      setNotes("");
    }
    prevRecordTypeRef.current = recordType;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordType, record]);

  // On mount, check sessionStorage for existing extraction data and apply base fields
  useEffect(() => {
    if (!memberId || record) return;
    const stored = loadExtraction(memberId);
    if (stored && stored.batches.length > 0) {
      const latestBatch = stored.batches[0];
      const bf = latestBatch.baseFields;
      if (bf.record_type && !getValues("record_type")) {
        setValue("record_type", bf.record_type as RecordType);
      }
      if (bf.record_date && !getValues("record_date")) {
        setValue("record_date", toDisplayDate(bf.record_date));
      }
      if (bf.diagnosis && !getValues("diagnosis")) {
        setValue("diagnosis", bf.diagnosis);
      }
      if (bf.next_review_date && !getValues("next_review_date")) {
        setValue("next_review_date", toDisplayDate(bf.next_review_date));
      }
      // Restore custom fields from stored extraction
      const customFields = ["chief_complaint", "existing_conditions", "investigations"] as const;
      for (const key of customFields) {
        const val = bf[key];
        if (val) {
          setCustomValues((prev) => (prev[key] ? prev : { ...prev, [key]: val }));
        }
      }
      // Restore provider match
      if (bf.provider_name && providerList.length > 0 && !getValues("provider_id")) {
        const match = providerList.find(
          (p) =>
            p.name.toLowerCase().includes(bf.provider_name!.toLowerCase()) ||
            bf.provider_name!.toLowerCase().includes(p.name.toLowerCase())
        );
        if (match) setValue("provider_id", match.id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberId, record]);

  const clinicalDataRef = useRef<HTMLInputElement>(null);

  function handleCustomFieldChange(key: string, value: string) {
    setCustomValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleTableChange(tableKey: string, rows: Record<string, string>[]) {
    setTableData((prev) => ({ ...prev, [tableKey]: rows }));
  }

  // Auto-fill batches — single sessionStorage read, memoized
  const {
    prescriptionBatches: _prescriptionBatches,
    labTestBatches: _labTestBatches,
    eyeglassBatches: _eyeglassBatches,
    allAutoFillBatches,
  } = useMemo(() => {
    if (!memberId)
      return {
        prescriptionBatches: [],
        labTestBatches: [],
        eyeglassBatches: [],
        allAutoFillBatches: [],
      };
    const prescriptionBatches = getBatchesForType(memberId, "prescriptions");
    const labTestBatches = getBatchesForType(memberId, "labTests");
    const eyeglassBatches =
      recordType === "rx_eyeglass" ? getBatchesForType(memberId, "eyeglass") : [];

    // Aggregate batches relevant to current form tables
    const relevant: import("@/lib/extraction-store").ExtractionBatch[] = [];
    for (const tableDef of tables) {
      if (tableDef.key === "prescriptions") relevant.push(...prescriptionBatches);
      else if (tableDef.key === "tests" || tableDef.key === "lab_results")
        relevant.push(...labTestBatches);
    }
    if (recordType === "rx_eyeglass") relevant.push(...eyeglassBatches);
    const seen = new Set<string>();
    const allAutoFillBatches = relevant.filter((b) => {
      if (seen.has(b.id)) return false;
      seen.add(b.id);
      return true;
    });

    return {
      prescriptionBatches: prescriptionBatches,
      labTestBatches: labTestBatches,
      eyeglassBatches: eyeglassBatches,
      allAutoFillBatches,
    };
  }, [memberId, recordType, tables]);

  // Handle auto-fill for a specific table
  function handleTableAutoFill(tableKey: string, batchId: string) {
    if (!memberId) return;

    const type =
      tableKey === "prescriptions"
        ? ("prescriptions" as const)
        : tableKey === "tests" || tableKey === "lab_results"
          ? ("labTests" as const)
          : undefined;
    if (!type) return;

    const data = consumeBatch(memberId, batchId, type);
    if (data && Array.isArray(data)) {
      setTableData((prev) => ({
        ...prev,
        [tableKey]: [...(prev[tableKey] || []), ...data],
      }));
    }
    refreshRecentBatches();
  }

  // Handle eyeglass auto-fill
  function _handleEyeglassAutoFill(batchId: string) {
    if (!memberId || recordType !== "rx_eyeglass") return;
    const data = consumeBatch(memberId, batchId, "eyeglass");
    if (data && !Array.isArray(data)) {
      setCustomValues((prev) => {
        const merged = { ...prev };
        for (const [k, v] of Object.entries(data)) {
          if (v && !merged[k]) merged[k] = v;
        }
        return merged;
      });
    }
    refreshRecentBatches();
  }

  // Get recent extraction batches — deferred to avoid hydration mismatch (sessionStorage is client-only)
  const [recentBatches, setRecentBatches] = useState<
    import("@/lib/extraction-store").ExtractionBatch[]
  >([]);
  const _storeHasData = recentBatches.length > 0;

  const refreshRecentBatches = useCallback(() => {
    if (!memberId) return;
    const stored = loadExtraction(memberId);
    setRecentBatches(stored ? stored.batches : []);
  }, [memberId]);

  useEffect(() => {
    if (!memberId || record) return;
    refreshRecentBatches();
  }, [memberId, record, refreshRecentBatches]);

  // Handle clicking a recent batch to auto-fill its data
  function handleRecentBatchClick(batchId: string) {
    if (!memberId) return;
    const stored = loadExtraction(memberId);
    if (!stored) return;
    const batch = stored.batches.find((b) => b.id === batchId);
    if (!batch) return;

    // Apply base fields if not already set
    const bf = batch.baseFields;
    if (bf.record_date && getValues("record_date") === todayStr()) {
      setValue("record_date", toDisplayDate(bf.record_date));
    }
    if (bf.diagnosis && !getValues("diagnosis")) {
      setValue("diagnosis", bf.diagnosis);
    }

    // Consume prescriptions
    if (batch.prescriptions.length > 0) {
      const rxData = consumeBatch(memberId, batchId, "prescriptions");
      if (rxData && Array.isArray(rxData)) {
        setTableData((prev) => ({
          ...prev,
          prescriptions: [...(prev.prescriptions || []), ...rxData],
        }));
      }
    }

    // Consume lab tests
    if (batch.labTests.length > 0) {
      const labData = consumeBatch(memberId, batchId, "labTests");
      if (labData && Array.isArray(labData)) {
        const labKey =
          tables.find((t) => t.key === "tests" || t.key === "lab_results")?.key || "lab_results";
        setTableData((prev) => ({
          ...prev,
          [labKey]: [...(prev[labKey] || []), ...labData],
        }));
      }
    }

    refreshRecentBatches();
  }

  // Get prescription rows from current table data
  const prescriptionRows = (tableData["prescriptions"] || []).filter((row) => row.medicine?.trim());
  const hasPrescriptions = prescriptionRows.length > 0;

  // Serialize clinical data into hidden field
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
    // Convert DD-MM-YYYY → YYYY-MM-DD for API
    const dateVal = getValues("record_date");
    if (dateVal) setValue("record_date", toISODate(dateVal));
    const reviewVal = getValues("next_review_date");
    if (reviewVal) setValue("next_review_date", toISODate(reviewVal));
  }

  function resetForm() {
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
    setStagingFileIds([]);
    setUploadedFiles([]);
    setExtracting(false);
    setExtractError(null);
    setProgress({ step: "", pct: 0, substeps: [], done: [] });
    setExtractedFields(new Set());
    setCustomValues({});
    setTableData({});
    setNotes("");
    setTags([]);
    setTagInput("");
    pendingExtractedFields.current = null;
    if (memberId) {
      sessionStorage.removeItem(`extraction_${memberId}`);
      refreshRecentBatches();
    }
  }

  // Intercept form submit: serialize structured data, then submit manually
  // to ensure the FormData includes updated values (React 19 captures
  // FormData before onSubmit runs, so direct DOM mutations in onSubmit
  // are missed by the form action).
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (isPending || !formRef.current) return;
    serializeToHiddenField();

    // Show prompt for new doctor visits with prescriptions
    if (!record && recordType === "doctor_visit" && hasPrescriptions) {
      setShowMedPrompt(true);
      return;
    }

    // Build fresh FormData from the updated DOM and submit manually
    const formData = new FormData(formRef.current);
    startTransition(() => {
      formAction(formData);
    });
  }

  // Directly submit via formAction (bypasses onSubmit cycle)
  function submitViaAction(updateMedications = true) {
    if (!formRef.current || isPending) return;
    serializeToHiddenField();
    const formData = new FormData(formRef.current);

    // "Save Only" — mark clinical_data so backend medication service skips it
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
          /* not JSON — leave as-is */
        }
      }
    }

    startTransition(() => {
      formAction(formData);
    });
    setShowMedPrompt(false);
  }

  function _registerExtracted(fieldName: keyof FormValues) {
    const reg = register(fieldName);
    const origOnChange = reg.onChange;
    return {
      ...reg,
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        setExtractedFields((prev) => {
          const next = new Set(prev);
          next.delete(fieldName);
          return next;
        });
        return origOnChange?.(e);
      },
    };
  }

  // Pending extracted custom fields — re-applied after recordType reset effect
  const pendingExtractedFields = useRef<Record<string, string> | null>(null);

  function mergeExtracted(
    extracted: ExtractionResponse["extracted"],
    stagingId: string,
    fileName: string
  ): boolean {
    const populated = new Set<string>();

    // ── record_type ──
    if (extracted.record_type && VALID_RECORD_TYPES.has(extracted.record_type)) {
      setValue("record_type", extracted.record_type as RecordType);
      populated.add("record_type");
    }

    // ── record_date ──
    const dateISO = normalizeDate(extracted.record_date);
    if (dateISO) {
      setValue("record_date", toDisplayDate(dateISO));
      populated.add("record_date");
    }

    // ── record_time (backend may return HH:MM:SS) ──
    const timeStr = normalizeTime(extracted.record_time);
    if (timeStr) {
      setValue("record_time", timeStr);
      populated.add("record_time");
    }

    // ── next_review_date (accept any valid date, past or future) ──
    const reviewISO = normalizeDate(extracted.next_review_date);
    if (reviewISO) {
      setValue("next_review_date", toDisplayDate(reviewISO));
      populated.add("next_review_date");
    }

    // ── Text fields (append-style) ──
    const diag = sanitizeText(extracted.diagnosis);
    if (diag) {
      const existing = getValues("diagnosis") || "";
      setValue("diagnosis", existing ? `${existing}; ${diag}` : diag);
      populated.add("diagnosis");
    }
    const clinData = sanitizeText(extracted.clinical_data, 5000);
    if (clinData) {
      const existing = getValues("clinical_data") || "";
      setValue("clinical_data", existing ? `${existing}\n\n${clinData}` : clinData);
      populated.add("clinical_data");
    }
    const rxText = sanitizeText(extracted.prescription_text, 2000);
    if (rxText) {
      const existing = getValues("prescription_text") || "";
      setValue("prescription_text", existing ? `${existing}\n\n${rxText}` : rxText);
      populated.add("prescription_text");
    }

    // ── Provider matching ──
    const provName = sanitizeText(extracted.provider_name, 200);
    if (provName && providerList.length > 0) {
      const lower = provName.toLowerCase();
      const match = providerList.find((p) => {
        const pLower = p.name.toLowerCase();
        return (
          (pLower.length >= 3 && lower.includes(pLower.slice(0, Math.min(pLower.length, 8)))) ||
          (lower.length >= 3 && pLower.includes(lower.slice(0, Math.min(lower.length, 8))))
        );
      });
      if (match) {
        setValue("provider_id", match.id);
        populated.add("provider_id");
      }
    }

    // ── Custom text fields ──
    const customFieldMap: Record<string, string | null> = {
      chief_complaint: sanitizeText(extracted.chief_complaint),
      existing_conditions: sanitizeText(extracted.existing_conditions),
      investigations: sanitizeText(extracted.investigations),
    };
    const pendingCustom: Record<string, string> = {};
    for (const [fieldKey, val] of Object.entries(customFieldMap)) {
      if (val) {
        pendingCustom[fieldKey] = val;
        populated.add(fieldKey);
      }
    }
    pendingExtractedFields.current = Object.keys(pendingCustom).length > 0 ? pendingCustom : null;
    if (Object.keys(pendingCustom).length > 0) {
      setCustomValues((prev) => ({ ...prev, ...pendingCustom }));
    }

    // ── Prescription table rows ──
    if (Array.isArray(extracted.prescriptions) && extracted.prescriptions.length > 0) {
      const validRows = extracted.prescriptions
        .map((row) => validatePrescriptionRow(row))
        .filter(Boolean) as Record<string, string>[];
      if (validRows.length > 0) {
        setTableData((prev) => ({
          ...prev,
          prescriptions: [...(prev.prescriptions || []), ...validRows],
        }));
        populated.add("prescriptions");
      }
    }

    // ── Lab test table rows ──
    if (Array.isArray(extracted.lab_tests) && extracted.lab_tests.length > 0) {
      const validRows = extracted.lab_tests
        .map((row) => validateLabTestRow(row))
        .filter(Boolean) as Record<string, string>[];
      if (validRows.length > 0) {
        setTableData((prev) => {
          const labKey =
            tables.find((t) => t.key === "tests" || t.key === "lab_results")?.key || "lab_results";
          return {
            ...prev,
            [labKey]: [...(prev[labKey] || []), ...validRows],
          };
        });
        populated.add("lab_tests");
      }
    }

    // ── Eyeglass data ──
    if (extracted.eyeglass && typeof extracted.eyeglass === "object") {
      const validEntries = Object.entries(extracted.eyeglass).filter(
        ([, v]) => typeof v === "string" && v.trim().length > 0
      );
      if (validEntries.length >= 2) {
        const eyeglass: Record<string, string> = {};
        for (const [k, v] of validEntries) eyeglass[k] = (v as string).trim();
        setCustomValues((prev) => {
          const merged = { ...prev };
          for (const [k, v] of Object.entries(eyeglass)) {
            if (v && !merged[k]) merged[k] = v;
          }
          return merged;
        });
        populated.add("eyeglass");
      }
    }

    // ── Persist to sessionStorage ──
    if (memberId) {
      saveExtraction(memberId, {
        fileName,
        prescriptions: Array.isArray(extracted.prescriptions)
          ? (extracted.prescriptions.map(validatePrescriptionRow).filter(Boolean) as Record<
              string,
              string
            >[])
          : [],
        labTests: Array.isArray(extracted.lab_tests)
          ? (extracted.lab_tests.map(validateLabTestRow).filter(Boolean) as Record<
              string,
              string
            >[])
          : [],
        eyeglass: extracted.eyeglass || null,
        baseFields: {
          record_type:
            extracted.record_type && VALID_RECORD_TYPES.has(extracted.record_type)
              ? extracted.record_type
              : undefined,
          record_date: dateISO || undefined,
          provider_name: provName || undefined,
          diagnosis: diag || undefined,
          next_review_date: reviewISO || undefined,
          chief_complaint: customFieldMap.chief_complaint || undefined,
          existing_conditions: customFieldMap.existing_conditions || undefined,
          investigations: customFieldMap.investigations || undefined,
        },
      });
      refreshRecentBatches();
    }

    if (populated.size > 0) {
      setExtractedFields((prev) => {
        const next = new Set(prev);
        populated.forEach((f) => next.add(f));
        return next;
      });
    }
    setStagingFileIds((prev) => [...prev, stagingId]);
    setUploadedFiles((prev) => [...prev, { name: fileName, stagingId }]);
    return populated.size > 0;
  }

  function appendExtractError(fileName: string, reason?: string) {
    const msg = reason || "unexpected error";
    setExtractError((prev) => (prev ? `${prev}; ${fileName}: ${msg}` : `${fileName}: ${msg}`));
  }

  async function extractFile(file: File): Promise<{ data?: ExtractionResponse; error?: string }> {
    const formData = new FormData();
    formData.append("file", file);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), EXTRACT_TIMEOUT);

    try {
      const response = await fetch(`${API_BASE}/members/${memberId}/records/extract`, {
        method: "POST",
        body: formData,
        credentials: "include",
        signal: controller.signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const msg =
          body?.detail ||
          body?.message ||
          (response.status === 401
            ? "Session expired — please log in again"
            : response.status === 413
              ? "File too large for the server"
              : response.status >= 500
                ? "Server error — please try again"
                : "Extraction failed");
        return { error: msg };
      }
      const result: ExtractionResponse = await response.json();
      return { data: result };
    } catch (e) {
      if (controller.signal.aborted) {
        return {
          error:
            "Extraction timed out — the document may be too large or complex. Try a smaller file.",
        };
      }
      if (e instanceof TypeError && e.message === "Failed to fetch") {
        return { error: "Network error — check your connection and try again." };
      }
      return { error: e instanceof Error ? e.message : "Extraction failed" };
    } finally {
      clearTimeout(timer);
    }
  }

  async function handleMultiFileExtract() {
    if (!memberId || !fileInputRef.current?.files?.length) return;

    const files = Array.from(fileInputRef.current.files);

    for (const file of files) {
      if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
        setExtractError(`Invalid file type: ${file.name}. Accepted: PDF, JPEG, PNG.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setExtractError(`File too large: ${file.name}. Maximum size is 25MB.`);
        return;
      }
    }

    setExtracting(true);
    setExtractError(null);
    const allDone: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const basePct = Math.round((i / files.length) * 100);
      const filePct = Math.round(100 / files.length);

      // Stage 1: Uploading
      setProgress({
        step: `Uploading ${i + 1}/${files.length}: ${file.name}`,
        pct: basePct + Math.round(filePct * 0.15),
        substeps: [
          "Uploading file...",
          "AI analyzing document...",
          "Extracting medical data...",
          "Auto-filling form...",
        ],
        done: [...allDone],
      });

      await new Promise((r) => setTimeout(r, 100));

      try {
        // Stage 2: AI Processing (fetch in progress)
        setProgress((prev) => ({
          ...prev,
          step: `Analyzing ${i + 1}/${files.length}: ${file.name}`,
          pct: basePct + Math.round(filePct * 0.4),
          substeps: [
            "Uploading file...",
            "AI analyzing document...",
            "Extracting medical data...",
            "Auto-filling form...",
          ],
          done: [...allDone, "Uploading file..."],
        }));

        const result = await extractFile(file);

        if (result.error) {
          allDone.push(`${file.name}: failed`);
          setExtractError((prev) =>
            prev ? `${prev}; ${file.name}: ${result.error}` : `${file.name}: ${result.error}`
          );
          continue;
        }

        if (result.data) {
          // Stage 3: Extracting data
          setProgress((prev) => ({
            ...prev,
            step: `Extracting ${i + 1}/${files.length}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.75),
            substeps: [
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
              "Auto-filling form...",
            ],
            done: [...allDone, "Uploading file...", "AI analyzing document..."],
          }));

          await new Promise((r) => setTimeout(r, 50));

          const hadData = mergeExtracted(
            result.data.extracted,
            result.data.staging_file_id,
            file.name
          );

          // Stage 4: Auto-filling
          setProgress((prev) => ({
            ...prev,
            step: `Auto-filling ${i + 1}/${files.length}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.95),
            substeps: [
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
              "Auto-filling form...",
            ],
            done: [
              ...allDone,
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
            ],
          }));

          await new Promise((r) => setTimeout(r, 50));

          allDone.push(file.name);

          if (!hadData) {
            setExtractError((prev) =>
              prev
                ? `${prev}; ${file.name}: no readable data found`
                : `${file.name}: no readable data found in document`
            );
          }
        }
      } catch (e) {
        allDone.push(`${file.name}: failed`);
        appendExtractError(file.name, e instanceof Error ? e.message : undefined);
      }
    }

    setProgress({ step: "Complete", pct: 100, substeps: [], done: [] });
    setExtracting(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileDrop(files: File[]) {
    if (!memberId || !files.length) return;

    for (const file of files) {
      if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
        setExtractError(`Invalid file type: ${file.name}. Accepted: PDF, JPEG, PNG.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setExtractError(`File too large: ${file.name}. Maximum size is 25MB.`);
        return;
      }
    }

    setExtracting(true);
    setExtractError(null);
    const allDone: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const basePct = Math.round((i / files.length) * 100);
      const filePct = Math.round(100 / files.length);

      setProgress({
        step: `Uploading ${i + 1}/${files.length}: ${file.name}`,
        pct: basePct + Math.round(filePct * 0.15),
        substeps: [
          "Uploading file...",
          "AI analyzing document...",
          "Extracting medical data...",
          "Auto-filling form...",
        ],
        done: [...allDone],
      });
      await new Promise((r) => setTimeout(r, 100));

      try {
        setProgress((prev) => ({
          ...prev,
          step: `Analyzing ${i + 1}/${files.length}: ${file.name}`,
          pct: basePct + Math.round(filePct * 0.4),
          substeps: [
            "Uploading file...",
            "AI analyzing document...",
            "Extracting medical data...",
            "Auto-filling form...",
          ],
          done: [...allDone, "Uploading file..."],
        }));
        const result = await extractFile(file);

        if (result.error) {
          allDone.push(`${file.name}: failed`);
          setExtractError((prev) =>
            prev ? `${prev}; ${file.name}: ${result.error}` : `${file.name}: ${result.error}`
          );
          continue;
        }
        if (result.data) {
          setProgress((prev) => ({
            ...prev,
            step: `Extracting ${i + 1}/${files.length}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.75),
            substeps: [
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
              "Auto-filling form...",
            ],
            done: [...allDone, "Uploading file...", "AI analyzing document..."],
          }));
          await new Promise((r) => setTimeout(r, 50));

          const hadData = mergeExtracted(
            result.data.extracted,
            result.data.staging_file_id,
            file.name
          );

          setProgress((prev) => ({
            ...prev,
            step: `Auto-filling ${i + 1}/${files.length}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.95),
            substeps: [
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
              "Auto-filling form...",
            ],
            done: [
              ...allDone,
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
            ],
          }));
          await new Promise((r) => setTimeout(r, 50));
          allDone.push(file.name);

          if (!hadData) {
            setExtractError((prev) =>
              prev
                ? `${prev}; ${file.name}: no readable data found`
                : `${file.name}: no readable data found in document`
            );
          }
        }
      } catch (e) {
        allDone.push(`${file.name}: failed`);
        appendExtractError(file.name, e instanceof Error ? e.message : undefined);
      }
    }

    setProgress({ step: "Complete", pct: 100, substeps: [], done: [] });
    setExtracting(false);
  }

  const hasCustomFields = config && config.customFields.length > 0;
  const hasTables = tables.length > 0;
  const hasStructuredContent = hasCustomFields || hasTables;
  const isDoctorVisit = recordType === "doctor_visit";

  // Memoize filtered config to avoid re-rendering TypeSpecificFields every render
  const typeSpecificConfig = useMemo(() => {
    if (!config) return null;
    if (isDoctorVisit) {
      // Chief complaint rendered in Visit Details; notes rendered after Diagnosis;
      // tables (prescription, lab results) rendered at the bottom
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

  // Warn on navigation if form is dirty
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
                onSaveComplete?.();
              }
            })
            .catch(() => onSaveComplete?.());
        });
      } else if (result.success) {
        onSaveComplete?.();
      }
    }
    prevPendingRef.current = isPending;
  }, [isPending, state, memberId, onSaveComplete]);

  return (
    <form ref={formRef} action={formAction} onSubmit={handleSubmit} className="space-y-2 max-w-3xl">
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

      {/* ═══ SECTION 1: Upload & Extract ═══ */}
      {memberId && !record && (
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

          {/* Upload drop zone */}
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
            className={`flex items-center justify-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm transition-all cursor-pointer ${
              isDragOver
                ? "border-primary bg-primary/10"
                : "border-muted-foreground/20 hover:border-primary/40 hover:bg-primary/5"
            }`}
          >
            <Upload className="h-4 w-4 text-muted-foreground/50" />
            <span className="text-muted-foreground">Drop or click to upload PDF, JPEG, PNG</span>
          </div>

          {/* Progress */}
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

          {/* Extracted files summary */}
          {uploadedFiles.length > 0 && !extracting && (
            <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-950">
              <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-medium text-green-700 dark:text-green-400">
                  Extracted {uploadedFiles.length} file{uploadedFiles.length !== 1 ? "s" : ""} —
                  review data below
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

          {/* Recent Files — show stored batches */}
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
                  className="text-[10px] text-muted-foreground hover:text-destructive transition-colors"
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
                        <span className="text-[10px] text-muted-foreground/60 flex items-center gap-0.5">
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
      )}

      {/* ═══ SECTION 2: Visit Details ═══ */}
      <div className="space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Visit Details
        </p>

        {/* Record type + Date in one row */}
        <div className="grid gap-2 md:grid-cols-2">
          <div className="space-y-0.5">
            <Label className="text-xs">Record Type</Label>
            <input type="hidden" name="record_type" value={recordType ?? ""} />
            <Select
              value={recordType ?? ""}
              onValueChange={(v) => {
                if (v) setValue("record_type", v as RecordType);
              }}
            >
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                {RECORD_TYPE_OPTIONS.map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.record_type && (
              <p id="err-record_type" role="alert" className="text-[11px] text-destructive">
                {errors.record_type.message}
              </p>
            )}
          </div>
          <div className="space-y-0.5">
            <Label htmlFor="record_date" className="text-xs">
              Date
            </Label>
            <Input
              id="record_date"
              type="text"
              placeholder="DD-MM-YYYY"
              aria-describedby="err-record_date"
              {...register("record_date")}
              className="h-8"
            />
            {errors.record_date && (
              <p id="err-record_date" role="alert" className="text-[11px] text-destructive">
                {errors.record_date.message}
              </p>
            )}
          </div>
        </div>

        {/* Provider/Consultant */}
        {config?.schemaFields.provider_id && (
          <div className="space-y-0.5">
            <Label htmlFor="provider_id" className="text-xs">
              {isDoctorVisit ? "Consultant" : "Provider"}
            </Label>
            {providerList.length > 0 ? (
              <select
                id="provider_id"
                {...register("provider_id")}
                className="flex h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onChange={(e) => {
                  if (e.target.value === "__add_new__") {
                    e.target.value = "";
                    setShowAddProvider(true);
                  } else {
                    register("provider_id").onChange(e);
                  }
                }}
              >
                <option value="">Select {isDoctorVisit ? "consultant" : "provider"}...</option>
                {providerList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.speciality ? ` - ${p.speciality}` : ""}
                  </option>
                ))}
                <option value="__add_new__">+ Add new provider...</option>
              </select>
            ) : (
              <div className="flex gap-1.5">
                <Input
                  id="provider_id"
                  {...register("provider_id")}
                  placeholder="e.g. Dr. Smith"
                  className="h-8 flex-1"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  onClick={() => setShowAddProvider(true)}
                >
                  <Plus className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Add Provider Dialog */}
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

        {/* Chief Complaint — prominent, for doctor_visit */}
        {isDoctorVisit && (
          <div className="space-y-0.5">
            <Label className="text-xs">Chief Complaint</Label>
            <Textarea
              rows={1}
              placeholder="Describe the main reason for the visit..."
              className="text-sm"
              value={customValues["chief_complaint"] || ""}
              onChange={(e) => handleCustomFieldChange("chief_complaint", e.target.value)}
            />
          </div>
        )}
      </div>

      {/* ═══ SECTION 3: Type-specific fields + tables ═══ */}
      {typeSpecificConfig && (
        <TypeSpecificFields
          config={typeSpecificConfig}
          values={customValues}
          onChange={handleCustomFieldChange}
          tableData={tableData}
          onTableChange={handleTableChange}
          onAutoFillBatch={handleTableAutoFill}
          autoFillBatches={allAutoFillBatches}
        />
      )}

      {/* Diagnosis — placed after Investigation tables */}
      {config?.schemaFields.diagnosis && (
        <div className="space-y-0.5">
          <Label htmlFor="diagnosis" className="text-xs">
            Diagnosis
          </Label>
          <Input
            id="diagnosis"
            {...register("diagnosis")}
            placeholder="Diagnosis if any"
            className="h-8"
          />
        </div>
      )}

      {/* Notes — placed after Diagnosis for doctor visits */}
      {isDoctorVisit && (
        <div className="space-y-0.5">
          <Label className="text-xs">Notes</Label>
          <Textarea
            rows={1}
            placeholder="Additional observations, advice..."
            className="text-sm"
            value={customValues["notes"] || ""}
            onChange={(e) => handleCustomFieldChange("notes", e.target.value)}
          />
        </div>
      )}

      {/* Fallback clinical_data textarea for misc_record */}
      {!hasStructuredContent && (
        <div className="space-y-0.5">
          <Label htmlFor="clinical_data" className="text-xs">
            Clinical Data
          </Label>
          <Textarea
            id="clinical_data"
            {...register("clinical_data")}
            rows={3}
            placeholder="Enter clinical data, observations, notes..."
            className="text-sm"
            onChange={(e) => {
              if (clinicalDataRef.current) clinicalDataRef.current.value = e.target.value;
              register("clinical_data").onChange(e);
            }}
          />
        </div>
      )}

      {/* Additional Notes for structured types */}
      {hasStructuredContent && !isDoctorVisit && (
        <div className="space-y-0.5">
          <Label htmlFor="additional_notes" className="text-xs">
            Notes (optional)
          </Label>
          <Textarea
            id="additional_notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={1}
            placeholder="Any additional notes..."
            className="text-sm"
          />
        </div>
      )}

      {/* ═══ SECTION 4: Follow-up ═══ */}
      {config?.schemaFields.next_review_date && (
        <div className="space-y-0.5">
          <Label htmlFor="next_review_date" className="text-xs">
            Next Review Date
          </Label>
          <Input
            id="next_review_date"
            type="text"
            placeholder="DD-MM-YYYY"
            {...register("next_review_date")}
            className="h-8"
          />
        </div>
      )}

      {/* Tags */}
      <div className="space-y-1">
        <Label className="text-xs">Tags</Label>
        <input type="hidden" name="tags" value={JSON.stringify(tags.length > 0 ? tags : null)} />
        <div className="flex gap-2">
          <Input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const v = tagInput.trim();
                if (v && !tags.includes(v)) {
                  setTags([...tags, v]);
                  setTagInput("");
                }
              }
            }}
            placeholder="Add tag, press Enter"
            className="h-8 flex-1"
          />
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="gap-1 text-xs">
                {t}
                <button
                  type="button"
                  onClick={() => setTags(tags.filter((x) => x !== t))}
                  className="hover:opacity-70"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* ═══ Prescription & Lab Results (doctor visit — at bottom) ═══ */}
      {isDoctorVisit &&
        tables.map((tableDef) => {
          const autoFillDataType =
            tableDef.key === "prescriptions"
              ? ("prescriptions" as const)
              : tableDef.key === "tests" || tableDef.key === "lab_results"
                ? ("labTests" as const)
                : undefined;
          return (
            <DynamicTable
              key={tableDef.key}
              def={tableDef}
              rows={tableData[tableDef.key] || []}
              onChange={(rows) => handleTableChange(tableDef.key, rows)}
              onAutoFillBatch={
                handleTableAutoFill
                  ? (batchId: string) => handleTableAutoFill(tableDef.key, batchId)
                  : undefined
              }
              autoFillBatches={allAutoFillBatches}
              autoFillDataType={autoFillDataType}
            />
          );
        })}

      {/* Save button */}
      <div className="flex gap-2">
        {!record && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={resetForm}
            disabled={isPending}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            Clear
          </Button>
        )}
        <Button type="submit" disabled={isPending} size="sm">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {isPending ? "Saving..." : record ? "Update Record" : "Create Record"}
        </Button>
      </div>

      {/* Medication update confirmation dialog */}
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
                  <th className="pb-1 text-left text-[10px] font-semibold text-muted-foreground uppercase">
                    Type
                  </th>
                  <th className="pb-1 px-2 text-left text-[10px] font-semibold text-muted-foreground uppercase">
                    Medicine
                  </th>
                  <th className="pb-1 px-2 text-left text-[10px] font-semibold text-muted-foreground uppercase">
                    Dose
                  </th>
                  <th className="pb-1 px-2 text-left text-[10px] font-semibold text-muted-foreground uppercase">
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowMedPrompt(false);
              }}
            >
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

      {/* Medication Sync Dialog — shown after save when med changes detected */}
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
