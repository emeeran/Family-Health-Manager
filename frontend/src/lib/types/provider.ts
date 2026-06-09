import type { ProviderType } from "./enums";

export interface ProviderCreate {
  name: string;
  provider_type?: ProviderType;
  speciality?: string | null;
  phone?: string | null;
  address?: string | null;
}

export interface ProviderUpdate {
  name?: string | null;
  provider_type?: ProviderType | null;
  speciality?: string | null;
  phone?: string | null;
  address?: string | null;
}

export interface AssignedMember {
  family_member_id: string;
  family_member_name: string;
  uhid: string | null;
  visit_count: number;
}

export interface ProviderResponse {
  id: string;
  household_id: string;
  name: string;
  provider_type: ProviderType;
  speciality: string | null;
  phone: string | null;
  address: string | null;
  created_at: string;
  assigned_members: AssignedMember[];
}
