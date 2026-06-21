import { apiRequest, streamRequest } from "../api-client";
import type {
  HealthRecordCreate,
  HealthRecordUpdate,
  HealthRecordResponse,
  ExtractionResponse,
  BatchExtractionResponse,
  CheckFilenamesResponse,
  TimelineResponse,
  LabRecordsResponse,
  RecordInsightResponse,
  DedupResponse,
} from "../types/health-record";
import type { RecordType } from "../types/enums";

export function listRecords(
  memberId: string,
  params?: {
    record_type?: RecordType;
    date_from?: string;
    date_to?: string;
    search?: string;
    cursor?: string;
    limit?: number;
  }
) {
  return apiRequest<HealthRecordResponse[]>(`/members/${memberId}/records`, {
    params: params as Record<string, string | undefined>,
  });
}

export function createRecord(
  memberId: string,
  data: HealthRecordCreate,
  stagingFileIds?: string,
  originalFileNames?: string
) {
  const params: Record<string, string | undefined> = {};
  if (stagingFileIds) params.staging_file_ids = stagingFileIds;
  if (originalFileNames) params.original_file_names = originalFileNames;
  return apiRequest<HealthRecordResponse>(`/members/${memberId}/records`, {
    method: "POST",
    body: data,
    params: Object.keys(params).length > 0 ? params : undefined,
  });
}

export function extractFromDocument(memberId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<ExtractionResponse>(`/members/${memberId}/records/extract`, {
    method: "POST",
    body: formData,
    isFormData: true,
  });
}

/**
 * Directory uploads and CPU-only providers (Ollama medgemma ~20 tok/s) make a
 * single batch run for many minutes. apiRequest's 30s default would abort the
 * fetch mid-extraction ("Request timed out"), so allow the request to live as
 * long as the backend's SSE streaming cap (1800s).
 */
const BATCH_EXTRACT_TIMEOUT = 1_800_000;

export function batchExtract(memberId: string, files: File[]) {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  return apiRequest<BatchExtractionResponse>(`/members/${memberId}/records/extract-batch`, {
    method: "POST",
    body: formData,
    isFormData: true,
    timeout: BATCH_EXTRACT_TIMEOUT,
  });
}

/**
 * Streaming variant of {@link batchExtract}. The non-streaming endpoint blocks
 * for the entire multi-file CPU extraction (many minutes on Ollama) with no
 * bytes on the wire, so the idle connection gets severed → "Network error".
 * This streams one `file_complete` event per file plus 15s heartbeats that keep
 * the connection alive — mirroring `extractDocumentStream`. `streamRequest`
 * already carries the 30-min timeout, 401 refresh, and a `cancel()` that the
 * caller wires into its abort path.
 *
 * SSE events: `{stage:"start",total}` → `{stage:"file_complete",index,total,item}`
 * (one per file, completion order) → `{stage:"done",total}` | `{stage:"error",message}`.
 */
export function batchExtractStream(
  memberId: string,
  files: File[],
  onEvent: (event: Record<string, unknown>) => void
) {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  return streamRequest(`/members/${memberId}/records/extract-batch/stream`, {
    body: formData,
    isFormData: true,
    onEvent,
  });
}

/**
 * Stream extraction progress + result over SSE (Phase 2). Emits events:
 * {stage:"secured"} → {stage:"extracting"} → {stage:"complete", extracted, ...}
 * | {stage:"error", message}. The blocking extractFromDocument is retained as
 * a fallback path for callers that don't stream.
 */
export function extractDocumentStream(
  memberId: string,
  file: File,
  onEvent: (event: Record<string, unknown>) => void
) {
  const formData = new FormData();
  formData.append("file", file);
  return streamRequest(`/members/${memberId}/records/extract/stream`, {
    body: formData,
    isFormData: true,
    onEvent,
  });
}

export function checkFilenames(memberId: string, filenames: string[]) {
  return apiRequest<CheckFilenamesResponse>(`/members/${memberId}/records/check-filenames`, {
    method: "POST",
    body: { filenames },
  });
}

export function getRecord(memberId: string, recordId: string) {
  return apiRequest<HealthRecordResponse>(`/members/${memberId}/records/${recordId}`);
}

export function updateRecord(memberId: string, recordId: string, data: HealthRecordUpdate) {
  return apiRequest<HealthRecordResponse>(`/members/${memberId}/records/${recordId}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteRecord(memberId: string, recordId: string) {
  return apiRequest<void>(`/members/${memberId}/records/${recordId}`, { method: "DELETE" });
}

export interface CleanupResponse {
  removed: number;
}

export function cleanupEmptyRecords(memberId: string) {
  return apiRequest<CleanupResponse>(`/members/${memberId}/records/cleanup`, {
    method: "POST",
  });
}

export function batchDeleteRecords(memberId: string, recordIds: string[]) {
  return apiRequest<{ deleted: number }>(`/members/${memberId}/records/batch-delete`, {
    method: "POST",
    body: { record_ids: recordIds },
  });
}

export function getTimeline(memberId: string, params?: Record<string, string | undefined>) {
  return apiRequest<TimelineResponse>(`/members/${memberId}/records/timeline/list`, {
    params,
  });
}

export function getLabRecords(memberId: string) {
  return apiRequest<LabRecordsResponse>(`/members/${memberId}/records/lab-records`);
}

export interface NLParseResponse {
  member: { id: string; name: string; matched_by: string } | null;
  record_type: string | null;
  record_date: string | null;
  record_time: string | null;
  diagnosis: string | null;
  chief_complaint: string | null;
  existing_conditions: string | null;
  investigations: string | null;
  provider_name: string | null;
  prescription_text: string | null;
  prescriptions: Record<string, string>[] | null;
  lab_tests: Record<string, string>[] | null;
  clinical_notes: string | null;
  next_review_date: string | null;
  glucose_value: string | null;
  meal_timing: string | null;
  hba1c_value: string | null;
  weight: string | null;
  height: string | null;
  blood_pressure: string | null;
  heart_rate: string | null;
  temperature: string | null;
  confidence: string;
  preview_fields: { label: string; value: string }[];
}

export function parseNaturalLanguage(text: string) {
  return apiRequest<NLParseResponse>("/smart-entry/parse-nl", {
    method: "POST",
    body: { text },
  });
}

export interface SmartSearchResult {
  id: string;
  member_name: string;
  record_type: string;
  record_date: string;
  diagnosis: string | null;
  preview: string | null;
}

export interface SmartSearchResponse {
  results: SmartSearchResult[];
  ai_powered: boolean;
}

export function smartSearchRecords(query: string) {
  return apiRequest<SmartSearchResponse>("/smart-search/records", {
    method: "POST",
    body: { query },
  });
}

export function getRecordInsight(memberId: string, recordId: string) {
  return apiRequest<RecordInsightResponse>(`/members/${memberId}/records/${recordId}/insight`);
}

export function findDuplicates(memberId: string) {
  return apiRequest<DedupResponse>(`/members/${memberId}/records/dedup`);
}

export function mergeRecords(memberId: string, keeperId: string, loserIds: string[]) {
  return apiRequest<HealthRecordResponse>(`/members/${memberId}/records/merge`, {
    method: "POST",
    body: { keeper_id: keeperId, loser_ids: loserIds },
  });
}

export function regenerateSummary(memberId: string, recordId: string) {
  return apiRequest<HealthRecordResponse>(
    `/members/${memberId}/records/${recordId}/regenerate-summary`,
    { method: "POST" }
  );
}

export function regenerateReport(memberId: string, recordId: string) {
  return apiRequest<HealthRecordResponse>(
    `/members/${memberId}/records/${recordId}/regenerate-report`,
    { method: "POST" }
  );
}

export interface BackfillSummariesResponse {
  updated_count: number;
  error_count?: number;
  total_remaining: number;
  message: string;
}

export function backfillSummaries(memberId: string, limit = 10) {
  return apiRequest<BackfillSummariesResponse>(`/members/${memberId}/records/backfill-summaries`, {
    method: "POST",
    params: { limit: String(limit) },
  });
}
