/**
 * Structured Smart Report types — mirror the backend Pydantic models in
 * `backend/app/schemas/smart_report.py`. The backend parses the LLM's JSON
 * payload out of the stored response string and ships it as a first-class
 * `report` object, so every field is optional: a tolerant parser means a
 * partial or slightly-off model output still renders.
 */

export interface LabParameterValue {
  date?: string | null;
  value?: string | null;
}

export type ParameterStatus = "in_range" | "out_of_range" | "borderline" | "critical" | string;
export type Trend =
  | "improved"
  | "further_decreased"
  | "stable"
  | "new_abnormal"
  | "not_available"
  | string;
export type SystemStatus = "needs_attention" | "ideal" | "no_data" | string;
export type Priority = "high" | "medium" | "low" | string;

export interface LabParameter {
  name?: string | null;
  value?: string | null;
  unit?: string | null;
  date?: string | null;
  status?: ParameterStatus | null;
  reference_range?: string | null;
  trend?: Trend | null;
  previous_values?: LabParameterValue[];
}

export interface SystemGlance {
  system?: string | null;
  status?: SystemStatus | null;
  summary?: string | null;
  parameters_total?: number;
  parameters_out_of_range?: number;
  parameters_improved?: number;
}

export interface OrganDetail {
  system?: string | null;
  parameters?: LabParameter[];
}

export interface ParameterInFocus {
  name?: string | null;
  system?: string | null;
  explanation?: string | null;
  significance?: string | null;
  trend_note?: string | null;
  recommendation?: string | null;
}

export interface SmartRecommendation {
  category?: string | null;
  priority?: Priority | null;
  action?: string | null;
  reasoning?: string | null;
}

export interface SmartReportData {
  systems_at_a_glance?: SystemGlance[];
  organ_details?: OrganDetail[];
  parameters_in_focus?: ParameterInFocus[];
  recommendations?: SmartRecommendation[];
  /** Tolerate extra LLM-emitted keys (backend uses extra="allow"). */
  [key: string]: unknown;
}
