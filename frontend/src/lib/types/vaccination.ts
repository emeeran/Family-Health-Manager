export interface VaccinationCreate {
  name: string;
  date_administered: string;
  booster_due_date?: string | null;
  notes?: string | null;
}

export interface VaccinationUpdate {
  name?: string | null;
  date_administered?: string | null;
  booster_due_date?: string | null;
  notes?: string | null;
}

export interface VaccinationResponse {
  id: string;
  family_member_id: string;
  name: string;
  date_administered: string;
  booster_due_date: string | null;
  notes: string | null;
  created_at: string;
}
