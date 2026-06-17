import type {
  RecordType,
  ReminderType,
  ScheduleType,
  Gender,
  Relationship,
  ProviderType,
} from "./types/enums";

/**
 * Resolve the API base URL.
 *
 * Precedence: runtime override (`window.__API_BASE__`, set by the static
 * runtime-config.js so a single build can be repointed without rebuilding) →
 * build-time `VITE_API_URL` → a relative `/api/v1` (the default, which works
 * behind the bundled Caddy reverse proxy with no configuration).
 *
 * The resolved value is the FULL base including `/api/v1`.
 */
function resolveApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const runtime = (window as unknown as { __API_BASE__?: string }).__API_BASE__;
    if (runtime) return runtime;
  }
  return import.meta.env.VITE_API_URL || "/api/v1";
}

export const API_BASE_URL = resolveApiBaseUrl();

export const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25MB
export const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

export const RECORD_TYPE_LABELS: Record<RecordType, string> = {
  doctor_visit: "Doctor Visit",
  lab_report: "Lab Report",
  rx_eyeglass: "Rx. Eyeglass",
  blood_glucose: "Blood Glucose / HbA1c",
  hba1c: "HbA1c",
  misc_record: "Misc Record",
  vitals: "Vitals",
  parkinsons_log: "PD Symptom Log",
};

export const REMINDER_TYPE_LABELS: Record<ReminderType, string> = {
  appointment: "Appointment",
  medication: "Medication",
  follow_up: "Follow-up",
  check_up: "Check-up",
  prescription_refill: "Prescription Refill",
};

export const SCHEDULE_TYPE_LABELS: Record<ScheduleType, string> = {
  once: "Once",
  daily: "Daily",
  weekly: "Weekly",
  custom: "Custom",
};

export const GENDER_LABELS: Record<Gender, string> = {
  male: "Male",
  female: "Female",
  other: "Other",
  prefer_not_to_say: "Prefer not to say",
};

export const RELATIONSHIP_LABELS: Record<Relationship, string> = {
  self: "Self",
  wife: "Wife",
  son: "Son",
  daughter: "Daughter",
  grand_son: "Grand son",
  grand_daughter: "Grand daughter",
  daughter_in_law: "Daughter-in-law",
  son_in_law: "Son-in-law",
  others: "Others",
};

export const BLOOD_GROUP_OPTIONS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] as const;

export const BMI_CATEGORY_COLORS: Record<string, string> = {
  Underweight: "bg-blue-100 text-blue-700",
  Normal: "bg-green-100 text-green-700",
  Overweight: "bg-yellow-100 text-yellow-700",
  Obese: "bg-red-100 text-red-700",
};

export const HBA1C_CATEGORY_COLORS: Record<string, string> = {
  Normal: "bg-green-100 text-green-700",
  Prediabetes: "bg-yellow-100 text-yellow-700",
  Diabetes: "bg-red-100 text-red-700",
};

export const PROVIDER_TYPE_LABELS: Record<ProviderType, string> = {
  doctor: "Doctor",
  lab_service: "Lab Service",
  hospital: "Hospital",
  other: "Other",
};

export const PROVIDER_TYPE_COLORS: Record<ProviderType, string> = {
  doctor: "from-violet-500 to-blue-500",
  lab_service: "from-emerald-500 to-teal-500",
  hospital: "from-red-500 to-rose-500",
  other: "from-amber-500 to-orange-500",
};
