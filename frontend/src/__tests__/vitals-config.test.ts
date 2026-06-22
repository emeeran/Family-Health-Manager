import { getConfig, RECORD_TYPE_CONFIGS } from "@/lib/record-type-configs";
import { serializeClinicalData } from "@/lib/clinical-data";
import { extractSummary } from "@/lib/record-utils";
import { VALID_RECORD_TYPES } from "@/components/records/record-form-utils";
import type { HealthRecordResponse } from "@/lib/types/health-record";

describe("vitals record type (#8)", () => {
  it("has a dedicated config with structured fields (not aliased to misc_record)", () => {
    const vitals = getConfig("vitals");
    const misc = getConfig("misc_record");
    expect(vitals).not.toBe(misc);

    const keys = vitals.customFields.map((f) => f.key);
    expect(keys).toEqual(
      expect.arrayContaining(["blood_pressure", "heart_rate", "temperature", "weight"])
    );
  });

  it("serializes vitals into structured clinical_data", () => {
    const result = serializeClinicalData(
      "vitals",
      { blood_pressure: "120/80", heart_rate: "72", temperature: "98.6", weight: "72.5" },
      {}
    );
    const parsed = JSON.parse(result);
    expect(parsed._type).toBe("structured");
    expect(parsed.blood_pressure).toBe("120/80");
    expect(parsed.heart_rate).toBe("72");
  });

  it("renders vitals using the canonical keys in extractSummary", () => {
    const clinical_data = serializeClinicalData(
      "vitals",
      { blood_pressure: "120/80", heart_rate: "72", temperature: "98.6", weight: "72.5" },
      {}
    );
    const record = { clinical_data } as unknown as HealthRecordResponse;
    const summary = extractSummary(record);
    expect(summary).toContain("BP: 120/80");
    expect(summary).toContain("Pulse: 72");
    expect(summary).toContain("Wt: 72.5kg");
  });
});

describe("hba1c type visibility (#11)", () => {
  it("is present in VALID_RECORD_TYPES so extraction/NL can select it", () => {
    expect(VALID_RECORD_TYPES.has("hba1c")).toBe(true);
  });

  it("has a registered config", () => {
    expect(RECORD_TYPE_CONFIGS.hba1c).toBeDefined();
    const keys = getConfig("hba1c").customFields.map((f) => f.key);
    expect(keys).toContain("hba1c_value");
  });
});
