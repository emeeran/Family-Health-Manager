/** Custom hook for PDF/image upload + AI extraction logic in RecordForm. */
import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import {
  VALID_RECORD_TYPES,
  normalizeDate,
  sanitizeText,
  validatePrescriptionRow,
  validateLabTestRow,
} from "./record-form-utils";
import type { FormValues } from "./record-form-utils";
import { todayISO } from "@/lib/quick-record";
import { getConfig, getTables } from "@/lib/record-type-configs";
import { mergeExtractedFields } from "./merge-extracted";
import {
  saveExtraction,
  consumeBatch,
  loadExtraction,
  getBatchesForType,
  removeBatch,
  clearExtraction,
} from "@/lib/extraction-store";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ExtractionResponse, ExtractedFields } from "@/lib/types/health-record";
import { extractDocumentStream } from "@/lib/api/records";
import type { UseFormReturn } from "react-hook-form";

interface UploadedFile {
  name: string;
  stagingId: string;
}

interface ExtractionState {
  extracting: boolean;
  extractError: string | null;
  progress: {
    step: string;
    pct: number;
    substeps: string[];
    done: string[];
  };
  uploadedFiles: UploadedFile[];
  stagingFileIds: string[];
  recentBatches: import("@/lib/extraction-store").ExtractionBatch[];
}

interface UseFileExtractionArgs {
  memberId?: string;
  record?: { clinical_data?: string; tags?: string[] | null } | null;
  recordType: RecordType | undefined;
  providerList: ProviderResponse[];
  form: UseFormReturn<FormValues>;
  customValues: Record<string, string>;
  setCustomValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  tableData: Record<string, Record<string, string>[]>;
  setTableData: React.Dispatch<React.SetStateAction<Record<string, Record<string, string>[]>>>;
  setNotes: React.Dispatch<React.SetStateAction<string>>;
  setExtractedFields: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export function useFileExtraction({
  memberId,
  record,
  recordType,
  providerList,
  form,
  customValues,
  setCustomValues,
  tableData,
  setTableData,
  setNotes,
  setExtractedFields,
}: UseFileExtractionArgs) {
  const { setValue, getValues } = form;
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
  const [_extractedFields, setExtractedFieldsLocal] = useState<Set<string>>(new Set());
  const [transcription, setTranscription] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingExtractedFields = useRef<Record<string, string> | null>(null);

  const [recentBatches, setRecentBatches] = useState<
    import("@/lib/extraction-store").ExtractionBatch[]
  >([]);

  const tables = useMemo(() => (recordType ? getTables(getConfig(recordType)) : []), [recordType]);

  const refreshRecentBatches = useCallback(() => {
    if (!memberId) return;
    const stored = loadExtraction(memberId);
    setRecentBatches(stored ? stored.batches : []);
  }, [memberId]);

  useEffect(() => {
    if (!memberId || record) return;
    refreshRecentBatches();
  }, [memberId, record, refreshRecentBatches]);

  // Auto-fill batches
  const { allAutoFillBatches } = useMemo(() => {
    if (!memberId) return { allAutoFillBatches: [] };
    const prescriptionBatches = getBatchesForType(memberId, "prescriptions");
    const labTestBatches = getBatchesForType(memberId, "labTests");
    const eyeglassBatches =
      recordType === "rx_eyeglass" ? getBatchesForType(memberId, "eyeglass") : [];
    const relevant: import("@/lib/extraction-store").ExtractionBatch[] = [];
    for (const tableDef of tables) {
      if (tableDef.key === "prescriptions") relevant.push(...prescriptionBatches);
      else if (tableDef.key === "tests" || tableDef.key === "lab_results")
        relevant.push(...labTestBatches);
    }
    if (recordType === "rx_eyeglass") relevant.push(...eyeglassBatches);
    const seen = new Set<string>();
    return {
      allAutoFillBatches: relevant.filter((b) => {
        if (seen.has(b.id)) return false;
        seen.add(b.id);
        return true;
      }),
    };
  }, [memberId, recordType, tables]);

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
      setTableData((prev) => ({ ...prev, [tableKey]: [...(prev[tableKey] || []), ...data] }));
    }
    refreshRecentBatches();
  }

  function handleRecentBatchClick(batchId: string) {
    if (!memberId) return;
    const stored = loadExtraction(memberId);
    if (!stored) return;
    const batch = stored.batches.find((b) => b.id === batchId);
    if (!batch) return;
    const bf = batch.baseFields;
    if (bf.record_date && getValues("record_date") === todayISO())
      setValue("record_date", bf.record_date);
    if (bf.diagnosis && !getValues("diagnosis")) setValue("diagnosis", bf.diagnosis);
    if (batch.prescriptions.length > 0) {
      const rxData = consumeBatch(memberId, batchId, "prescriptions");
      if (rxData && Array.isArray(rxData))
        setTableData((prev) => ({
          ...prev,
          prescriptions: [...(prev.prescriptions || []), ...rxData],
        }));
    }
    if (batch.labTests.length > 0) {
      const labData = consumeBatch(memberId, batchId, "labTests");
      if (labData && Array.isArray(labData)) {
        const labKey =
          tables.find((t) => t.key === "tests" || t.key === "lab_results")?.key || "lab_results";
        setTableData((prev) => ({ ...prev, [labKey]: [...(prev[labKey] || []), ...labData] }));
      }
    }
    refreshRecentBatches();
  }

  function mergeExtracted(response: ExtractionResponse): boolean {
    const {
      extracted,
      staging_file_id: stagingId,
      original_file_name: fileName,
      transcription: rawText,
    } = response;

    // Store transcription
    if (rawText) {
      setTranscription(rawText);
    }

    const { populated, pendingCustom } = mergeExtractedFields(
      {
        providerList,
        form: { setValue, getValues },
        setCustomValues,
        setTableData,
        setExtractedFields,
        tables,
      },
      extracted
    );
    pendingExtractedFields.current = pendingCustom;

    if (populated.size > 0) {
      setExtractedFieldsLocal((prev) => {
        const next = new Set(prev);
        populated.forEach((f) => next.add(f));
        return next;
      });
    }

    // Persist to the extraction store so recent batches can auto-fill later
    // (file-upload path only — NL extraction does not stage files).
    if (memberId) {
      const dateISO = normalizeDate(extracted.record_date);
      const reviewISO = normalizeDate(extracted.next_review_date);
      const diag = sanitizeText(extracted.diagnosis);
      const provName = sanitizeText(extracted.provider_name, 200);
      saveExtraction(memberId, {
        fileName: fileName || "unknown",
        transcription: rawText || null,
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
          chief_complaint: sanitizeText(extracted.chief_complaint) || undefined,
          existing_conditions: sanitizeText(extracted.existing_conditions) || undefined,
          investigations: sanitizeText(extracted.investigations) || undefined,
        },
      });
      refreshRecentBatches();
    }

    setStagingFileIds((prev) => [...prev, stagingId]);
    setUploadedFiles((prev) => [...prev, { name: fileName || "unknown", stagingId }]);
    return populated.size > 0;
  }

  async function extractFile(
    file: File,
    index: number,
    total: number,
    allDone: string[]
  ): Promise<{ data?: ExtractionResponse; error?: string }> {
    const basePct = Math.round((index / total) * 100);
    const filePct = Math.round(100 / total);
    const SUBSTEPS = [
      "Uploading file...",
      "AI analyzing document...",
      "Extracting medical data...",
      "Auto-filling form...",
    ];

    return new Promise<{ data?: ExtractionResponse; error?: string }>((resolve) => {
      let settled = false;
      const finish = (r: { data?: ExtractionResponse; error?: string }) => {
        if (!settled) {
          settled = true;
          resolve(r);
        }
      };

      if (!memberId) {
        finish({ error: "No member selected" });
        return;
      }

      const { promise } = extractDocumentStream(memberId, file, (event) => {
        const stage = event.stage as string;
        if (stage === "secured") {
          // Original is safely stored + encrypted — AI extraction now running.
          setProgress({
            step: `Analyzing ${index + 1}/${total}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.45),
            substeps: SUBSTEPS,
            done: [...allDone, "Uploading file..."],
          });
        } else if (stage === "complete") {
          setProgress((prev) => ({
            ...prev,
            step: `Extracting ${index + 1}/${total}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.8),
            done: [...allDone, "Uploading file...", "AI analyzing document..."],
          }));
          finish({
            data: {
              staging_file_id: (event.staging_file_id as string) || "",
              original_file_name: (event.original_file_name as string) ?? null,
              extracted: event.extracted as ExtractedFields,
              confidence: (event.confidence as string) ?? "medium",
              verification: null,
              transcription: (event.transcription as string) ?? null,
            },
          });
        } else if (stage === "error") {
          finish({ error: (event.message as string) || "Extraction failed" });
        }
      });

      promise.catch((e: unknown) => {
        finish({ error: e instanceof Error ? e.message : "Extraction failed" });
      });
    });
  }

  async function handleMultiFileExtract() {
    if (!memberId || !fileInputRef.current?.files?.length) return;
    const files = Array.from(fileInputRef.current.files);
    for (const file of files) {
      if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
        setExtractError(`Invalid file type: ${file.name}. Accepted: PDF, JPEG, PNG, WebP.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setExtractError(`File too large: ${file.name}. Maximum size is 25MB.`);
        return;
      }
    }
    await processFiles(files);
  }

  async function handleFileDrop(files: File[]) {
    if (!memberId || !files.length) return;
    for (const file of files) {
      if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
        setExtractError(`Invalid file type: ${file.name}. Accepted: PDF, JPEG, PNG, WebP.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setExtractError(`File too large: ${file.name}. Maximum size is 25MB.`);
        return;
      }
    }
    await processFiles(files);
  }

  async function processFiles(files: File[]) {
    setExtracting(true);
    setExtractError(null);
    const allDone: string[] = [];
    const SUBSTEPS = [
      "Uploading file...",
      "AI analyzing document...",
      "Extracting medical data...",
      "Auto-filling form...",
    ];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const basePct = Math.round((i / files.length) * 100);
      const filePct = Math.round(100 / files.length);

      setProgress({
        step: `Uploading ${i + 1}/${files.length}: ${file.name}`,
        pct: basePct + Math.round(filePct * 0.15),
        substeps: SUBSTEPS,
        done: [...allDone],
      });

      try {
        const result = await extractFile(file, i, files.length, allDone);

        if (result.error) {
          allDone.push(`${file.name}: failed`);
          setExtractError((prev) =>
            prev ? `${prev}; ${file.name}: ${result.error}` : `${file.name}: ${result.error}`
          );
          continue;
        }

        if (result.data) {
          const hadData = mergeExtracted(result.data);
          setProgress((prev) => ({
            ...prev,
            step: `Auto-filling ${i + 1}/${files.length}: ${file.name}`,
            pct: basePct + Math.round(filePct * 0.97),
            done: [
              ...allDone,
              "Uploading file...",
              "AI analyzing document...",
              "Extracting medical data...",
            ],
          }));
          allDone.push(file.name);
          if (!hadData)
            setExtractError((prev) =>
              prev
                ? `${prev}; ${file.name}: no readable data found`
                : `${file.name}: no readable data found in document`
            );
        }
      } catch (e) {
        allDone.push(`${file.name}: failed`);
        const msg = e instanceof Error ? e.message : undefined;
        setExtractError((prev) =>
          prev
            ? `${prev}; ${file.name}: ${msg || "unexpected error"}`
            : `${file.name}: ${msg || "unexpected error"}`
        );
      }
    }

    setProgress({ step: "Complete", pct: 100, substeps: [], done: [] });
    setExtracting(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // Restore extraction data from sessionStorage on mount
  useEffect(() => {
    if (!memberId || record) return;
    const stored = loadExtraction(memberId);
    if (stored && stored.batches.length > 0) {
      const bf = stored.batches[0].baseFields;
      if (bf.record_type && !getValues("record_type"))
        setValue("record_type", bf.record_type as RecordType);
      if (bf.record_date && !getValues("record_date")) setValue("record_date", bf.record_date);
      if (bf.diagnosis && !getValues("diagnosis")) setValue("diagnosis", bf.diagnosis);
      if (bf.next_review_date && !getValues("next_review_date"))
        setValue("next_review_date", bf.next_review_date);
      const customFields = ["chief_complaint", "existing_conditions", "investigations"] as const;
      for (const key of customFields) {
        const val = bf[key];
        if (val) setCustomValues((prev) => (prev[key] ? prev : { ...prev, [key]: val }));
      }
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

  function clearExtractionState() {
    setStagingFileIds([]);
    setUploadedFiles([]);
    setExtracting(false);
    setExtractError(null);
    setProgress({ step: "", pct: 0, substeps: [], done: [] });
    setExtractedFieldsLocal(new Set());
    setTranscription(null);
    pendingExtractedFields.current = null;
    if (memberId) {
      sessionStorage.removeItem(`extraction_${memberId}`);
      refreshRecentBatches();
    }
  }

  return {
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
    pendingExtractedFields,
    transcription,
    setTranscription,
  };
}
