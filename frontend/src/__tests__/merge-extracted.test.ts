import { describe, it, expect, vi } from "vitest";
import {
  mergeExtractedFields,
  extractedFromNL,
  typeSpecificFieldsFromNL,
  type MergeContext,
} from "@/components/records/merge-extracted";
import type { ExtractedFields } from "@/lib/types/health-record";
import type { NLParseResponse } from "@/lib/api/records";

// Build a MergeContext backed by vi.fn mocks (cast to satisfy the real types).
function makeCtx(): MergeContext {
  const ctx = {
    providerList: [],
    form: { setValue: vi.fn(), getValues: vi.fn(() => "") },
    setCustomValues: vi.fn(),
    setTableData: vi.fn(),
    setExtractedFields: vi.fn(),
    tables: [{ key: "lab_results", label: "Labs", fields: [] }],
  };
  return ctx as unknown as MergeContext;
}

const nilFields: ExtractedFields = {
  record_type: null,
  record_date: null,
  record_time: null,
  clinical_data: null,
  diagnosis: null,
  existing_conditions: null,
  chief_complaint: null,
  investigations: null,
  prescription_text: null,
  provider_name: null,
  next_review_date: null,
  prescriptions: null,
  lab_tests: null,
  eyeglass: null,
  weight: null,
  height: null,
  blood_pressure: null,
  heart_rate: null,
  temperature: null,
};

function lastUpdater(fn: unknown) {
  const calls = (fn as { mock: { calls: unknown[][] } }).mock.calls;
  return calls[0][0] as (prev: Record<string, unknown>) => Record<string, unknown>;
}

describe("mergeExtractedFields", () => {
  it("sets base form fields and returns populated keys", () => {
    const ctx = makeCtx();
    const { populated } = mergeExtractedFields(ctx, {
      ...nilFields,
      record_type: "blood_glucose",
      record_date: "2026-03-10",
      diagnosis: "T2DM",
    });
    expect(populated.has("record_type")).toBe(true);
    expect(populated.has("record_date")).toBe(true);
    expect(populated.has("diagnosis")).toBe(true);
    expect(ctx.form.setValue).toHaveBeenCalledWith("record_type", "blood_glucose");
  });

  it("merges type-specific custom fields (glucose/vitals) via extraCustomFields", () => {
    const ctx = makeCtx();
    mergeExtractedFields(ctx, nilFields, {
      glucose_value: "120",
      meal_timing: "before_food",
    });
    expect(lastUpdater(ctx.setCustomValues)({})).toEqual({
      glucose_value: "120",
      meal_timing: "before_food",
    });
  });

  it("appends prescription rows to tableData (normalized with defaults)", () => {
    const ctx = makeCtx();
    mergeExtractedFields(ctx, {
      ...nilFields,
      prescriptions: [{ medicine: "Metformin", dosage: "500mg" }],
    });
    const result = lastUpdater(ctx.setTableData)({});
    expect(result).toEqual({
      prescriptions: [
        expect.objectContaining({ medicine: "Metformin", dosage: "500mg", type: "Tab" }),
      ],
    });
  });

  it("drops prescription rows with no medicine", () => {
    const ctx = makeCtx();
    const { populated } = mergeExtractedFields(ctx, {
      ...nilFields,
      prescriptions: [{ dosage: "500mg" }],
    });
    expect(populated.has("prescriptions")).toBe(false);
    expect(ctx.setTableData).not.toHaveBeenCalled();
  });
});

describe("extractedFromNL", () => {
  it("maps NL fields into ExtractedFields shape (clinical_notes -> clinical_data)", () => {
    const parsed = {
      record_type: "doctor_visit",
      record_date: "2026-03-10",
      record_time: "09:30",
      diagnosis: "Headache",
      chief_complaint: "Headache",
      existing_conditions: null,
      investigations: null,
      provider_name: "Dr. Sharma",
      prescription_text: "ibuprofen",
      prescriptions: null,
      lab_tests: null,
      clinical_notes: "notes here",
      next_review_date: null,
    } as NLParseResponse;
    const extracted = extractedFromNL(parsed);
    expect(extracted.record_type).toBe("doctor_visit");
    expect(extracted.chief_complaint).toBe("Headache");
    expect(extracted.provider_name).toBe("Dr. Sharma");
    expect(extracted.clinical_data).toBe("notes here");
  });
});

describe("typeSpecificFieldsFromNL", () => {
  it("collects only non-empty type-specific fields", () => {
    const fields = typeSpecificFieldsFromNL({
      glucose_value: "110",
      meal_timing: "after_food",
      hba1c_value: null,
      weight: "",
      height: "172",
      blood_pressure: "120/80",
      heart_rate: null,
      temperature: null,
    } as NLParseResponse);
    expect(fields).toEqual({
      glucose_value: "110",
      meal_timing: "after_food",
      height: "172",
      blood_pressure: "120/80",
    });
  });
});
