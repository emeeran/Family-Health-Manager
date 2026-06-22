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

// ── On-server compressed backups (Data tab) ────────────────────────────────

export interface BackupArchive {
  name: string;
  size_bytes: number;
  created_at: string;
}

export interface BackupStatus {
  attachments_bytes: number;
  database_bytes: number;
  backups_bytes: number;
  disk: { total: number; used: number; free: number };
  last_run: string | null;
  last_archive: string | null;
}

export interface BackupRunResult {
  filename: string;
  size_bytes: number;
  created_at: string;
}
