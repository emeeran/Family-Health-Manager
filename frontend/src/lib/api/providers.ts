import { apiRequest } from "../api-client";
import type { ProviderCreate, ProviderUpdate, ProviderResponse } from "../types/provider";
import type { ProviderAssignmentResponse } from "../types/provider-assignment";

export function listProviders(params?: { speciality?: string }) {
  return apiRequest<ProviderResponse[]>("/providers", { params });
}

export function createProvider(data: ProviderCreate) {
  return apiRequest<ProviderResponse>("/providers", { method: "POST", body: data });
}

export function getProvider(providerId: string) {
  return apiRequest<ProviderResponse>(`/providers/${providerId}`);
}

export function updateProvider(providerId: string, data: ProviderUpdate) {
  return apiRequest<ProviderResponse>(`/providers/${providerId}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteProvider(providerId: string) {
  return apiRequest<void>(`/providers/${providerId}`, { method: "DELETE" });
}

export function getProviderMembers(providerId: string) {
  return apiRequest<ProviderAssignmentResponse[]>(`/providers/${providerId}/members`);
}
