export interface HouseholdUpdate {
  name?: string | null;
}

export interface HouseholdResponse {
  id: string;
  name: string;
  primary_user_id: string;
  created_at: string;
}
