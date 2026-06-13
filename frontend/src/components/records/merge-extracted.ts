/**
 * Shared field-merging logic used by both document extraction (useFileExtraction)
 * and natural-language extraction (useNLExtraction). Keeps a single source of
 * truth for how AI-extracted data maps onto the record form.
 */
import type { UseFormReturn } from "react-hook-form";
import {
  VALID_RECORD_TYPES,
  normalizeDate,
  normalizeTime,
  sanitizeText,
  validatePrescriptionRow,
  validateLabTestRow,
} from "./record-form-utils";
import type { FormValues } from "./record-form-utils";
import { toDisplayDate } from "@/lib/utils";
import type { TableRowDef } from "@/lib/record-type-configs";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ExtractedFields } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";

export interface MergeContext {
  providerList: ProviderResponse[];
  form: Pick<UseFormReturn<FormValues>, "setValue" | "getValues">;
  setCustomValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setTableData: React.Dispatch<React.SetStateAction<Record<string, Record<string, string>[]>>>;
  setExtractedFields: React.Dispatch<React.SetStateAction<Set<string>>>;
  tables: TableRowDef[];
}

export interface MergeResult {
  /** Field keys that received a value. */
  populated: Set<string>;
  /** Custom-field values pending highlight (chief_complaint, type-specific, ...). */
  pendingCustom: Record<string, string> | null;
}

/**
 * Merge an ExtractedFields object into the form state.
 *
 * @param extraCustomFields Type-specific custom fields that aren't part of
 *   ExtractedFields (e.g. glucose_value, blood_pressure, hba1c_value). These are
 *   merged into customValues so vitals/glucose/HbA1c records populate too.
 */
export function mergeExtractedFields(
  ctx: MergeContext,
  extracted: ExtractedFields,
  extraCustomFields: Record<string, string> = {}
): MergeResult {
  const { providerList, form, setCustomValues, setTableData, setExtractedFields, tables } = ctx;
  const { setValue, getValues } = form;
  const populated = new Set<string>();

  if (extracted.record_type && VALID_RECORD_TYPES.has(extracted.record_type)) {
    setValue("record_type", extracted.record_type as RecordType);
    populated.add("record_type");
  }

  const dateISO = normalizeDate(extracted.record_date);
  if (dateISO) {
    setValue("record_date", toDisplayDate(dateISO));
    populated.add("record_date");
  }

  const timeStr = normalizeTime(extracted.record_time);
  if (timeStr) {
    setValue("record_time", timeStr);
    populated.add("record_time");
  }

  const reviewISO = normalizeDate(extracted.next_review_date);
  if (reviewISO) {
    setValue("next_review_date", toDisplayDate(reviewISO));
    populated.add("next_review_date");
  }

  const diag = sanitizeText(extracted.diagnosis);
  if (diag) {
    const existing = getValues("diagnosis") || "";
    setValue("diagnosis", existing ? `${existing}; ${diag}` : diag);
    populated.add("diagnosis");
  }
  const clinData = sanitizeText(extracted.clinical_data, 5000);
  if (clinData) {
    const existing = getValues("clinical_data") || "";
    setValue("clinical_data", existing ? `${existing}\n\n${clinData}` : clinData);
    populated.add("clinical_data");
  }
  const rxText = sanitizeText(extracted.prescription_text, 2000);
  if (rxText) {
    const existing = getValues("prescription_text") || "";
    setValue("prescription_text", existing ? `${existing}\n\n${rxText}` : rxText);
    populated.add("prescription_text");
  }

  const provName = sanitizeText(extracted.provider_name, 200);
  if (provName && providerList.length > 0) {
    const lower = provName.toLowerCase();
    const match = providerList.find((p) => {
      const pLower = p.name.toLowerCase();
      return (
        (pLower.length >= 3 && lower.includes(pLower.slice(0, Math.min(pLower.length, 8)))) ||
        (lower.length >= 3 && pLower.includes(lower.slice(0, Math.min(lower.length, 8))))
      );
    });
    if (match) {
      setValue("provider_id", match.id);
      populated.add("provider_id");
    }
  }

  // Standard custom fields + any extra type-specific custom fields
  const customFieldMap: Record<string, string | null> = {
    chief_complaint: sanitizeText(extracted.chief_complaint),
    existing_conditions: sanitizeText(extracted.existing_conditions),
    investigations: sanitizeText(extracted.investigations),
  };
  const pendingCustom: Record<string, string> = {};
  for (const [fieldKey, val] of Object.entries(customFieldMap)) {
    if (val) {
      pendingCustom[fieldKey] = val;
      populated.add(fieldKey);
    }
  }
  for (const [fieldKey, val] of Object.entries(extraCustomFields)) {
    const cleaned = sanitizeText(val);
    if (cleaned) {
      pendingCustom[fieldKey] = cleaned;
      populated.add(fieldKey);
    }
  }
  if (Object.keys(pendingCustom).length > 0)
    setCustomValues((prev) => ({ ...prev, ...pendingCustom }));

  if (Array.isArray(extracted.prescriptions) && extracted.prescriptions.length > 0) {
    const validRows = extracted.prescriptions
      .map(validatePrescriptionRow)
      .filter(Boolean) as Record<string, string>[];
    if (validRows.length > 0) {
      setTableData((prev) => ({
        ...prev,
        prescriptions: [...(prev.prescriptions || []), ...validRows],
      }));
      populated.add("prescriptions");
    }
  }

  if (Array.isArray(extracted.lab_tests) && extracted.lab_tests.length > 0) {
    const validRows = extracted.lab_tests.map(validateLabTestRow).filter(Boolean) as Record<
      string,
      string
    >[];
    if (validRows.length > 0) {
      setTableData((prev) => {
        const labKey =
          tables.find((t) => t.key === "tests" || t.key === "lab_results")?.key || "lab_results";
        return { ...prev, [labKey]: [...(prev[labKey] || []), ...validRows] };
      });
      populated.add("lab_tests");
    }
  }

  if (extracted.eyeglass && typeof extracted.eyeglass === "object") {
    const validEntries = Object.entries(extracted.eyeglass).filter(
      ([, v]) => typeof v === "string" && v.trim().length > 0
    );
    if (validEntries.length >= 2) {
      const eyeglass: Record<string, string> = {};
      for (const [k, v] of validEntries) eyeglass[k] = (v as string).trim();
      setCustomValues((prev) => {
        const merged = { ...prev };
        for (const [k, v] of Object.entries(eyeglass)) {
          if (v && !merged[k]) merged[k] = v;
        }
        return merged;
      });
      populated.add("eyeglass");
    }
  }

  if (populated.size > 0) {
    setExtractedFields((prev) => {
      const next = new Set(prev);
      populated.forEach((f) => next.add(f));
      return next;
    });
  }

  return {
    populated,
    pendingCustom: Object.keys(pendingCustom).length > 0 ? pendingCustom : null,
  };
}

/**
 * Build an ExtractedFields object from an NLParseResponse so it can be routed
 * through the same mergeExtractedFields logic as document extraction.
 */
export function extractedFromNL(parsed: {
  record_type: string | null;
  record_date: string | null;
  record_time: string | null;
  diagnosis: string | null;
  chief_complaint: string | null;
  existing_conditions: string | null;
  investigations: string | null;
  provider_name: string | null;
  prescription_text: string | null;
  prescriptions: Record<string, string>[] | null;
  lab_tests: Record<string, string>[] | null;
  clinical_notes: string | null;
  next_review_date: string | null;
}): ExtractedFields {
  return {
    record_type: parsed.record_type as RecordType | null,
    record_date: parsed.record_date,
    record_time: parsed.record_time,
    clinical_data: parsed.clinical_notes,
    diagnosis: parsed.diagnosis,
    existing_conditions: parsed.existing_conditions,
    chief_complaint: parsed.chief_complaint,
    investigations: parsed.investigations,
    prescription_text: parsed.prescription_text,
    provider_name: parsed.provider_name,
    next_review_date: parsed.next_review_date,
    prescriptions: parsed.prescriptions,
    lab_tests: parsed.lab_tests,
    eyeglass: null,
  };
}

/**
 * Collect type-specific custom fields (glucose/vitals/HbA1c) from an NLParseResponse
 * that aren't part of ExtractedFields but ARE valid custom-field keys per the configs.
 */
export function typeSpecificFieldsFromNL(parsed: {
  glucose_value: string | null;
  meal_timing: string | null;
  hba1c_value: string | null;
  weight: string | null;
  blood_pressure: string | null;
  heart_rate: string | null;
  temperature: string | null;
}): Record<string, string> {
  const fields: Record<string, string> = {};
  const pick = (val: string | null): string | null => {
    if (!val) return null;
    const s = String(val).trim();
    return s || null;
  };
  const entries: [string, string | null][] = [
    ["glucose_value", pick(parsed.glucose_value)],
    ["meal_timing", pick(parsed.meal_timing)],
    ["hba1c_value", pick(parsed.hba1c_value)],
    ["weight", pick(parsed.weight)],
    ["blood_pressure", pick(parsed.blood_pressure)],
    ["heart_rate", pick(parsed.heart_rate)],
    ["temperature", pick(parsed.temperature)],
  ];
  for (const [k, v] of entries) {
    if (v) fields[k] = v;
  }
  return fields;
}
