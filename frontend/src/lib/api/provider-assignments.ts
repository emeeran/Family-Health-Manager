import { apiRequest } from "../api-client";
import type {
  ProviderAssignmentCreate,
  ProviderAssignmentResponse,
} from "../types/provider-assignment";

export function listAssignments(memberId: string) {
  return apiRequest<ProviderAssignmentResponse[]>(`/members/${memberId}/providers`);
}

export function createAssignment(memberId: string, data: ProviderAssignmentCreate) {
  return apiRequest<ProviderAssignmentResponse>(`/members/${memberId}/providers`, {
    method: "POST",
    body: data,
  });
}

export function deleteAssignment(memberId: string, assignmentId: string) {
  return apiRequest<void>(`/members/${memberId}/providers/${assignmentId}`, {
    method: "DELETE",
  });
}

export function updateUhid(memberId: string, assignmentId: string, uhid: string | null) {
  return apiRequest<ProviderAssignmentResponse>(`/members/${memberId}/providers/${assignmentId}`, {
    method: "PATCH",
    body: { uhid },
  });
}
