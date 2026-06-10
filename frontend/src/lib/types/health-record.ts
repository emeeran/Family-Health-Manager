import type { RecordType } from "./enums";
import type { VerificationResult } from "./message";

export interface HealthRecordCreate {
  provider_id?: string | null;
  record_type: RecordType;
  record_date: string;
  record_time?: string | null;
  clinical_data: string;
  diagnosis?: string | null;
  prescription_text?: string | null;
  next_review_date?: string | null;
  tags?: string[] | null;
}

export interface HealthRecordUpdate {
  provider_id?: string | null;
  clinical_data?: string | null;
  diagnosis?: string | null;
  prescription_text?: string | null;
  next_review_date?: string | null;
  tags?: string[] | null;
}

export interface AttachmentBrief {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
}

export interface HealthRecordResponse {
  id: string;
  family_member_id: string;
  provider_id: string | null;
  provider_name: string | null;
  record_type: RecordType;
  record_date: string;
  record_time: string | null;
  clinical_data: string;
  diagnosis: string | null;
  prescription_text: string | null;
  next_review_date: string | null;
  tags: string[] | null;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  attachments?: AttachmentBrief[];
}

export interface ExtractedFields {
  record_type: RecordType | null;
  record_date: string | null;
  record_time: string | null;
  clinical_data: string | null;
  diagnosis: string | null;
  existing_conditions: string | null;
  chief_complaint: string | null;
  investigations: string | null;
  prescription_text: string | null;
  provider_name: string | null;
  next_review_date: string | null;
  prescriptions: Record<string, string>[] | null;
  lab_tests: Record<string, string>[] | null;
  eyeglass: Record<string, string> | null;
}

export interface ExtractionResponse {
  staging_file_id: string;
  original_file_name: string | null;
  extracted: ExtractedFields;
  confidence: string;
  verification: VerificationResult | null;
  transcription: string | null;
}

export interface TimelineResponse {
  items: HealthRecordResponse[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface LabRecordItem {
  id: string;
  record_type: RecordType;
  record_date: string;
  test_name: string;
  result: string;
  provider_name: string | null;
  doctor_name: string | null;
}

export interface LabRecordsResponse {
  items: LabRecordItem[];
}

export interface RecordInsight {
  id: string;
  prompt: string;
  response: string;
  provider_used: string;
  generated_at: string;
  verification: VerificationResult | null;
}

export interface RecordInsightResponse {
  insight: RecordInsight | null;
}

export interface BatchExtractionItem {
  filename: string;
  staging_file_id: string | null;
  extracted: ExtractedFields | null;
  transcription: string | null;
  is_duplicate: boolean;
  duplicate_of_id: string | null;
  duplicate_of_diagnosis: string | null;
  error: string | null;
  verification: VerificationResult | null;
}

export interface BatchExtractionResponse {
  extractions: BatchExtractionItem[];
}

export interface CheckFilenamesResponse {
  existing: string[];
}

export interface DuplicateRecordItem {
  id: string;
  record_type: RecordType;
  record_date: string;
  diagnosis: string | null;
  provider_name: string | null;
  provider_id: string | null;
  prescription_text: string | null;
  has_attachments: boolean;
  attachment_count: number;
  created_at: string;
}

export interface DuplicateGroup {
  records: DuplicateRecordItem[];
  recommended_keeper_id: string;
  match_reasons: string[];
  score: number;
}

export interface DedupResponse {
  groups: DuplicateGroup[];
  total_records_scanned: number;
}

export interface MedicationDiffRequest {
  prescriptions: Record<string, string>[];
  record_id?: string;
}

export interface MedicationDiffItem {
  medicine: string;
  type: string;
  old_dosage: string | null;
  new_dosage: string | null;
  old_timing: string | null;
  new_timing: string | null;
  old_duration: string | null;
  new_duration: string | null;
  provider_name: string | null;
}

export interface MedicationDiffResponse {
  added: MedicationDiffItem[];
  updated: MedicationDiffItem[];
  removed: MedicationDiffItem[];
  unchanged: MedicationDiffItem[];
}

export interface MedicationApplyRequest {
  apply_added: string[];
  apply_updated: string[];
  apply_removed: string[];
}
