export interface ProviderCreate {
  name: string;
  speciality?: string | null;
  phone?: string | null;
  address?: string | null;
}

export interface ProviderUpdate {
  name?: string | null;
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
  speciality: string | null;
  phone: string | null;
  address: string | null;
  created_at: string;
  assigned_members: AssignedMember[];
}
