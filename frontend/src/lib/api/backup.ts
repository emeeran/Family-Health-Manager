import { apiRequest } from "../api-client";
import { API_BASE_URL } from "../constants";
import type {
  BackupValidationResponse,
  BackupImportRequest,
  BackupImportResponse,
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
