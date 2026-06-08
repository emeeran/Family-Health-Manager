import { apiRequest } from "../api-client";
import type { HouseholdUpdate, HouseholdResponse } from "../types/household";
import type { HealthRecordResponse } from "../types/health-record";

export function getHousehold() {
  return apiRequest<HouseholdResponse>("/household");
}

export function updateHousehold(data: HouseholdUpdate) {
  return apiRequest<HouseholdResponse>("/household", { method: "PUT", body: data });
}

export function listHouseholdRecords(limit?: number) {
  return apiRequest<HealthRecordResponse[]>("/household/records", {
    params: limit ? { limit: String(limit) } : undefined,
  });
}

export function searchHouseholdRecords(query: string, limit?: number) {
  return apiRequest<HealthRecordResponse[]>("/household/records/search", {
    params: { q: query, ...(limit ? { limit: String(limit) } : {}) },
  });
}

export function resetDatabase(password: string, confirmation: string) {
  return apiRequest<{ message: string }>("/household/reset-database", {
    method: "POST",
    body: { password, confirmation },
  });
}
