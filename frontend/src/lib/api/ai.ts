import { apiRequest } from "../api-client";

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

export function getAIStatus() {
  return apiRequest<AIStatusResponse>("/ai/status", { timeout: 120_000 });
}
