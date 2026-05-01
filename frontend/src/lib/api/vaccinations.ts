import { apiRequest } from "../api-client";
import type {
  VaccinationCreate,
  VaccinationUpdate,
  VaccinationResponse,
} from "../types/vaccination";

export function listVaccinations(memberId: string) {
  return apiRequest<VaccinationResponse[]>(`/members/${memberId}/vaccinations`);
}

export function createVaccination(memberId: string, data: VaccinationCreate) {
  return apiRequest<VaccinationResponse>(`/members/${memberId}/vaccinations`, {
    method: "POST",
    body: data,
  });
}

export function updateVaccination(
  memberId: string,
  vaccinationId: string,
  data: VaccinationUpdate
) {
  return apiRequest<VaccinationResponse>(`/members/${memberId}/vaccinations/${vaccinationId}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteVaccination(memberId: string, vaccinationId: string) {
  return apiRequest<void>(`/members/${memberId}/vaccinations/${vaccinationId}`, {
    method: "DELETE",
  });
}
