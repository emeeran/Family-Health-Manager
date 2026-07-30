/** Structured medication-report payload (mirrors backend MedicationReportData). */
export interface Medicine {
  name?: string | null;
  dose_schedule?: string | null;
  indication?: string | null;
  key_note?: string | null;
}

export interface MedicationInteraction {
  pair?: string | null;
  severity?: string | null;
  explanation?: string | null;
  action?: string | null;
}

export interface MedicationRecommendation {
  priority?: string | null;
  action?: string | null;
}

export interface MedicationReportData {
  regimen_overview?: string | null;
  medicines?: Medicine[];
  interactions?: MedicationInteraction[];
  schedule_adherence?: string | null;
  safety_alerts?: string | null;
  recommendations?: MedicationRecommendation[];
}
