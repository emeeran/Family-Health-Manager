import { apiRequest } from "../api-client";
import type { AIInsightRequest, AIInsightResponse } from "../types/ai";

export interface ProviderStatus {
  name: string;
  id?: string;
  model?: string;
  available: boolean;
  response_ms?: number;
  error?: string;
}

export interface AIStatusResponse {
  providers: ProviderStatus[];
}

export function generateInsight(data: AIInsightRequest) {
  return apiRequest<AIInsightResponse>("/ai/insights", { method: "POST", body: data });
}

export function explainRecords(prompt?: string) {
  return apiRequest<AIInsightResponse>("/ai/explain", { method: "POST", body: { prompt } });
}

export function getAIStatus() {
  return apiRequest<AIStatusResponse>("/ai/status", { timeout: 120_000 });
}
