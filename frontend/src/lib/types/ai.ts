export interface AIInsightRequest {
  prompt: string;
  health_record_id?: string | null;
}

export interface AIInsightResponse {
  id: string;
  health_record_id: string | null;
  conversation_id: string | null;
  prompt: string;
  response: string;
  provider_used: string;
  generated_at: string;
  disclaimer: string;
}
