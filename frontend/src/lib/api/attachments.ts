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

/** Cookie-auth <img> URL for an attachment's server-generated thumbnail.
 *  Prefer this over getAttachmentBlob for previews: it fetches the small
 *  WebP/PNG thumbnail (not the full-resolution original) and lets the browser
 *  cache it, instead of downloading megabytes and allocating a blob URL. */
export function getAttachmentThumbnailUrl(attachmentId: string): string {
  return `${API_BASE_URL}/attachments/${attachmentId}/thumbnail`;
}
