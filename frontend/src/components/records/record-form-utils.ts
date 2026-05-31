/** Pure utilities and constants for RecordForm — no React dependencies. */
import { z } from "zod";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";

export const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : "/api/v1";

export const RECORD_TYPE_OPTIONS = Object.entries(RECORD_TYPE_LABELS) as [RecordType, string][];

export const VALID_RECORD_TYPES = new Set<string>([
  "doctor_visit",
  "lab_report",
  "rx_eyeglass",
  "blood_glucose",
  "misc_record",
  "vitals",
  "parkinsons_log",
]);

export const EXTRACT_TIMEOUT = 300_000; // 5 min
export const MEDICATION_SYNC_KEY = "_medication_sync";
export const VALID_MED_TYPES = new Set([
  "Tab",
  "Cap",
  "Inj",
  "Syp",
  "Cream",
  "Drops",
  "Inhaler",
  "Other",
]);
export const VALID_TIMINGS = new Set([
  "before_food",
  "after_food",
  "with_food",
  "empty_stomach",
  "bedtime",
  "sos",
  "stat",
]);

/** Normalize various date formats to YYYY-MM-DD, or return null */
export function normalizeDate(val: unknown): string | null {
  if (!val || typeof val !== "string") return null;
  const s = val.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const dmy = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return null;
}

/** Normalize time to HH:MM, handling HH:MM:SS from backend */
export function normalizeTime(val: unknown): string | null {
  if (!val || typeof val !== "string") return null;
  const s = val.trim();
  const m = s.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return null;
  const h = Number(m[1]);
  const mins = Number(m[2]);
  if (h < 0 || h > 23 || mins < 0 || mins > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

export function sanitizeText(val: unknown, maxLen = 500): string | null {
  if (!val || typeof val !== "string") return null;
  const trimmed = val.trim();
  if (!trimmed) return null;
  return trimmed.length > maxLen ? trimmed.slice(0, maxLen) : trimmed;
}

export function validatePrescriptionRow(row: unknown): Record<string, string> | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  const medicine = sanitizeText(r.medicine, 200);
  if (!medicine) return null;
  return {
    type: VALID_MED_TYPES.has(r.type as string) ? (r.type as string) : "Tab",
    medicine,
    dosage: sanitizeText(r.dosage, 50) || "",
    duration: sanitizeText(r.duration, 50) || "",
    timing: VALID_TIMINGS.has(r.timing as string) ? (r.timing as string) : "",
    note: sanitizeText(r.note, 200) || "",
  };
}

export function validateLabTestRow(row: unknown): Record<string, string> | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  const test_name = sanitizeText(r.test_name, 200);
  if (!test_name) return null;
  return {
    test_name,
    result: sanitizeText(r.result, 100) || "",
    ref_value: sanitizeText(r.ref_value, 100) || "",
    note: sanitizeText(r.note, 200) || "",
  };
}

export function todayStr() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}-${mm}-${d.getFullYear()}`;
}

export function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export const baseSchema = z.object({
  record_type: z.enum([
    "doctor_visit",
    "lab_report",
    "rx_eyeglass",
    "blood_glucose",
    "hba1c",
    "misc_record",
    "vitals",
    "parkinsons_log",
  ] as const),
  record_date: z.string().min(1, "Record date is required"),
  record_time: z.string().optional(),
  clinical_data: z.string().optional(),
  diagnosis: z.string().optional(),
  prescription_text: z.string().optional(),
  provider_id: z.string().optional(),
  next_review_date: z.string().optional(),
});

export type FormValues = z.infer<typeof baseSchema>;
