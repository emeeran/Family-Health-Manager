/** Structured pre-consultation note payload (mirrors backend PreConsultationData). */
export interface PreConsultationData {
  chronic_conditions?: string[];
  past_events?: string[];
  chief_complaints?: string[];
  lab_anomalies?: string[];
  medications?: string[];
  questions?: string[];
}
