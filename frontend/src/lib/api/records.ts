import { apiRequest } from "../api-client";
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

export function batchExtract(memberId: string, files: File[]) {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  return apiRequest<BatchExtractionResponse>(`/members/${memberId}/records/extract-batch`, {
    method: "POST",
    body: formData,
    isFormData: true,
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
  prescription_text: string | null;
  clinical_notes: string | null;
  next_review_date: string | null;
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
