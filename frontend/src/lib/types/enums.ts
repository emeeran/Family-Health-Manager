// Mirrors backend/app/models/base.py enums
export type Gender = "male" | "female" | "other" | "prefer_not_to_say";
export type Relationship =
  | "self"
  | "wife"
  | "son"
  | "daughter"
  | "grand_son"
  | "grand_daughter"
  | "daughter_in_law"
  | "son_in_law"
  | "others";
export type RecordType =
  | "doctor_visit"
  | "lab_report"
  | "rx_eyeglass"
  | "blood_glucose"
  | "hba1c"
  | "misc_record"
  | "vitals"
  | "parkinsons_log";
export type ReminderType =
  | "appointment"
  | "medication"
  | "follow_up"
  | "check_up"
  | "prescription_refill";
export type ScheduleType = "once" | "daily" | "weekly" | "custom";
export type MessageRole = "user" | "assistant" | "system";
export type ConversationScope = "member" | "general";
