import type { ConversationScope } from "./enums";

export interface ConversationCreate {
  family_member_id?: string | null;
  scope: ConversationScope;
  title?: string | null;
}

export interface ConversationResponse {
  id: string;
  household_id: string;
  family_member_id: string | null;
  scope: ConversationScope;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetailResponse {
  conversation: ConversationResponse;
  messages: import("./message").MessageResponse[];
}
