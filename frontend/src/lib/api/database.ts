import { apiRequest } from "../api-client";
import type { IntegrityReport, RepairOperation, RepairResponse } from "../types/database";

export async function getIntegrity(): Promise<IntegrityReport> {
  return apiRequest<IntegrityReport>("/database/integrity", { method: "GET" });
}

/**
 * Run a maintenance operation (admin). Throws ApiError(409) if a restore is
 * in progress, or ApiError(403) for non-admin users.
 */
export async function repairDatabase(operation: RepairOperation): Promise<RepairResponse> {
  return apiRequest<RepairResponse>("/database/repair", {
    method: "POST",
    body: { operation },
  });
}
