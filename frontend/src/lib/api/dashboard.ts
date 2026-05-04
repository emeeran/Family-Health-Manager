import { apiRequest } from "../api-client";
import type { DashboardSummary, RiskAssessment } from "../types/dashboard";

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>("/dashboard/summary");
}

export function getMemberComparison() {
  return apiRequest<DashboardSummary>("/dashboard/member-comparison");
}

export function getRiskAssessment(memberId: string) {
  return apiRequest<RiskAssessment>(`/members/${memberId}/risk-assessment`);
}
