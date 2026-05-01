export interface ProviderAssignmentCreate {
  provider_id: string;
  uhid?: string | null;
}

export interface ProviderAssignmentResponse {
  id: string;
  provider_id: string;
  provider_name: string;
  family_member_id: string;
  family_member_name: string;
  uhid: string | null;
  created_at: string;
}
