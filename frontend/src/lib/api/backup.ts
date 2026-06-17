import { apiRequest } from "../api-client";
import { API_BASE_URL } from "../constants";
import type {
  BackupValidationResponse,
  BackupImportRequest,
  BackupImportResponse,
  BackupArchive,
  BackupStatus,
  BackupRunResult,
} from "../types/backup";

export async function downloadBackupExport(): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/backup/export`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new Error("Backup export failed");
  return response.blob();
}

export async function validateBackup(file: File): Promise<BackupValidationResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<BackupValidationResponse>("/backup/validate", {
    method: "POST",
    body: formData,
    isFormData: true,
  });
}

export async function importBackup(data: BackupImportRequest): Promise<BackupImportResponse> {
  return apiRequest<BackupImportResponse>("/backup/import", {
    method: "POST",
    body: data,
  });
}

export async function cleanupStagedBackup(validationId: string): Promise<void> {
  return apiRequest<void>(`/backup/staging/${validationId}`, {
    method: "DELETE",
  });
}

// ── On-server compressed backups (Data tab) ────────────────────────────────

export async function getBackupStatus(): Promise<BackupStatus> {
  return apiRequest<BackupStatus>("/backup/status", { method: "GET" });
}

export async function listBackupArchives(): Promise<BackupArchive[]> {
  const data = await apiRequest<{ archives: BackupArchive[] }>("/backup/archives", {
    method: "GET",
  });
  return data.archives;
}

export async function runBackup(): Promise<BackupRunResult> {
  return apiRequest<BackupRunResult>("/backup/run", { method: "POST" });
}

export async function deleteBackupArchive(name: string): Promise<void> {
  return apiRequest<void>(`/backup/archives/${encodeURIComponent(name)}`, { method: "DELETE" });
}

/** URL for downloading an archive (same-origin GET sends the auth cookie). */
export function backupArchiveDownloadUrl(name: string): string {
  return `${API_BASE_URL}/backup/archives/${encodeURIComponent(name)}`;
}
