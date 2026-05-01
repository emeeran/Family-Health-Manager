export interface BackupCounts {
  members: number;
  providers: number;
  provider_assignments: number;
  health_records: number;
  attachments: number;
  ai_insights: number;
  conversations: number;
  messages: number;
  reminders: number;
  notifications: number;
}

export interface BackupManifest {
  version: string;
  app_version: string;
  created_at: string;
  household_name: string;
  household_id: string;
  counts: BackupCounts;
}

export type ImportMode = "merge" | "replace";

export interface BackupValidationResponse {
  validation_id: string;
  valid: boolean;
  manifest: BackupManifest | null;
  warnings: string[];
  errors: string[];
}

export interface BackupImportRequest {
  validation_id: string;
  mode: ImportMode;
}

export interface BackupImportResponse {
  imported: BackupCounts;
  skipped: BackupCounts;
  failed: number;
  errors: string[];
}
