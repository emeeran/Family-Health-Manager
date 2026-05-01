import { apiRequest } from "../api-client";
import type { AIInsightRequest, AIInsightResponse } from "../types/ai";

export function generateInsight(data: AIInsightRequest) {
  return apiRequest<AIInsightResponse>("/ai/insights", { method: "POST", body: data });
}

export function explainRecords(prompt?: string) {
  return apiRequest<AIInsightResponse>("/ai/explain", { method: "POST", body: { prompt } });
}
