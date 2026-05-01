import { apiRequest } from "../api-client";
import { API_BASE_URL } from "../constants";
import type { AttachmentResponse } from "../types/attachment";

export function uploadAttachment(recordId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<AttachmentResponse>(`/attachments/records/${recordId}`, {
    method: "POST",
    body: formData,
    isFormData: true,
  });
}

export async function getAttachmentBlob(attachmentId: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/attachments/${attachmentId}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error("Failed to download attachment");
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export function deleteAttachment(attachmentId: string) {
  return apiRequest<void>(`/attachments/${attachmentId}`, { method: "DELETE" });
}
