import type { MessageRole } from "./enums";

export interface MessageCreate {
  content: string;
}

export type VerificationStatus = "verified" | "warnings" | "unverifiable" | "pending" | "failed";
export type WarningType =
  | "wrong_date"
  | "wrong_value"
  | "wrong_member"
  | "wrong_gender"
  | "wrong_medication"
  | "wrong_diagnosis"
  | "omission"
  | "fabrication";

export interface VerificationWarning {
  type: WarningType;
  claim: string;
  correction: string;
  severity: "high" | "medium" | "low";
}

export interface VerificationResult {
  status: VerificationStatus;
  claims_checked: number;
  verifier_provider: string;
  summary: string | null;
  warnings: VerificationWarning[] | null;
  verified_at: string;
}

export interface MessageResponse {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  verification?: VerificationResult | null;
}

export interface SendMessageResponse {
  user_message: MessageResponse;
  assistant_message: MessageResponse;
  verification?: VerificationResult | null;
}
