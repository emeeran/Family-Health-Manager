import { apiRequest, streamRequest } from "../api-client";
import type {
  ConversationCreate,
  ConversationResponse,
  ConversationDetailResponse,
} from "../types/conversation";
import type { MessageCreate, SendMessageResponse, VerificationResult } from "../types/message";

export function listConversations() {
  return apiRequest<ConversationResponse[]>("/conversations");
}

export function createConversation(data: ConversationCreate) {
  return apiRequest<ConversationResponse>("/conversations", { method: "POST", body: data });
}

export function getConversation(conversationId: string) {
  return apiRequest<ConversationDetailResponse>(`/conversations/${conversationId}`);
}

export function deleteConversation(conversationId: string) {
  return apiRequest<void>(`/conversations/${conversationId}`, { method: "DELETE" });
}

export function updateConversation(conversationId: string, data: { title: string }) {
  return apiRequest<{ id: string; title: string }>(`/conversations/${conversationId}`, {
    method: "PATCH",
    body: data,
  });
}

export function sendMessage(conversationId: string, data: MessageCreate) {
  return apiRequest<SendMessageResponse>(`/conversations/${conversationId}/messages`, {
    method: "POST",
    body: data,
  });
}

export interface StreamEvent {
  stage: string;
  [key: string]: unknown;
}

export function sendMessageStream(
  conversationId: string,
  data: MessageCreate,
  onEvent: (event: StreamEvent) => void
): { promise: Promise<void>; cancel: () => void } {
  return streamRequest(`/conversations/${conversationId}/messages/stream`, {
    body: data,
    onEvent: onEvent as (event: Record<string, unknown>) => void,
  });
}

export function getMessageVerification(conversationId: string, messageId: string) {
  return apiRequest<VerificationResult>(
    `/conversations/${conversationId}/messages/${messageId}/verification`
  );
}
