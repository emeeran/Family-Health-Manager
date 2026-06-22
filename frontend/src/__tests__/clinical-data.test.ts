import {
  serializeClinicalData,
  deserializeClinicalData,
  isStructuredClinicalData,
} from "@/lib/clinical-data";

describe("clinical-data serialization", () => {
  describe("serializeClinicalData", () => {
    it("returns plain text for misc_record type with no config", () => {
      const result = serializeClinicalData("misc_record", { clinical_data: "plain text note" }, {});
      expect(result).toBe("plain text note");
    });

    it("serializes structured data with marker", () => {
      const result = serializeClinicalData(
        "doctor_visit",
        { chief_complaint: "Headache", notes: "Test notes" },
        { prescriptions: [{ medicine: "Aspirin", dosage: "100mg" }] },
        "Additional notes"
      );

      const parsed = JSON.parse(result);
      expect(parsed._type).toBe("structured");
      expect(parsed._version).toBe(1);
      expect(parsed._recordType).toBe("doctor_visit");
      expect(parsed.chief_complaint).toBe("Headache");
      expect(parsed.prescriptions).toEqual([{ medicine: "Aspirin", dosage: "100mg" }]);
      expect(parsed._notes).toBe("Additional notes");
    });

    it("omits empty custom fields", () => {
      const result = serializeClinicalData(
        "doctor_visit",
        { chief_complaint: "Fever", notes: "" },
        {}
      );
      const parsed = JSON.parse(result);
      expect(parsed.chief_complaint).toBe("Fever");
      expect(parsed).not.toHaveProperty("notes");
    });
  });

  describe("deserializeClinicalData", () => {
    it("deserializes structured JSON back to fields + tables", () => {
      const json = JSON.stringify({
        _type: "structured",
        _version: 1,
        _recordType: "doctor_visit",
        chief_complaint: "Headache",
        prescriptions: [{ medicine: "Aspirin", dosage: "100mg" }],
        _notes: "Test notes",
      });

      const result = deserializeClinicalData(json);
      expect(result.isStructured).toBe(true);
      expect(result.fields.chief_complaint).toBe("Headache");
      expect(result.tableData.prescriptions).toEqual([{ medicine: "Aspirin", dosage: "100mg" }]);
      expect(result.notes).toBe("Test notes");
    });

    it("handles plain text (non-structured) input", () => {
      const result = deserializeClinicalData("Just some plain text");
      expect(result.isStructured).toBe(false);
      expect(result.fields.clinical_data).toBe("Just some plain text");
    });

    it("handles empty string", () => {
      const result = deserializeClinicalData("");
      expect(result.isStructured).toBe(false);
      expect(result.fields).toEqual({});
    });
  });

  describe("isStructuredClinicalData", () => {
    it("returns true for structured data", () => {
      const json = JSON.stringify({ _type: "structured", _version: 1 });
      expect(isStructuredClinicalData(json)).toBe(true);
    });

    it("returns false for plain text", () => {
      expect(isStructuredClinicalData("plain text")).toBe(false);
    });

    it("returns false for empty string", () => {
      expect(isStructuredClinicalData("")).toBe(false);
    });
  });
});
