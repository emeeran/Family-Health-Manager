import { apiRequest } from "../api-client";
import type { VaccinationCreate, VaccinationResponse } from "../types/vaccination";

export function listVaccinations(memberId: string) {
  return apiRequest<VaccinationResponse[]>(`/members/${memberId}/vaccinations`);
}

export function createVaccination(memberId: string, data: VaccinationCreate) {
  return apiRequest<VaccinationResponse>(`/members/${memberId}/vaccinations`, {
    method: "POST",
    body: data,
  });
}

export function deleteVaccination(memberId: string, vaccinationId: string) {
  return apiRequest<void>(`/members/${memberId}/vaccinations/${vaccinationId}`, {
    method: "DELETE",
  });
}
