import { MED_TYPE_OPTIONS, TIMING_OPTIONS, MEAL_TIMING_OPTIONS } from "@/lib/record-type-configs";
import { VALID_MED_TYPES, VALID_TIMINGS } from "@/components/records/record-form-utils";

describe("option sets — single source of truth (#20)", () => {
  it("MED_TYPE_OPTIONS covers the standard medication types", () => {
    expect(MED_TYPE_OPTIONS.map((o) => o.value)).toEqual([
      "Tab",
      "Cap",
      "Inj",
      "Syp",
      "Cream",
      "Drops",
      "Inhaler",
      "Other",
    ]);
  });

  it("TIMING_OPTIONS covers the standard timings", () => {
    expect(TIMING_OPTIONS.map((o) => o.value)).toEqual([
      "before_food",
      "after_food",
      "with_food",
      "empty_stomach",
      "bedtime",
      "sos",
      "stat",
    ]);
  });

  it("VALID_MED_TYPES / VALID_TIMINGS are derived from the canonical options", () => {
    for (const o of MED_TYPE_OPTIONS) expect(VALID_MED_TYPES.has(o.value)).toBe(true);
    for (const o of TIMING_OPTIONS) expect(VALID_TIMINGS.has(o.value)).toBe(true);
    expect(VALID_MED_TYPES.has("Unknown")).toBe(false);
    expect(VALID_TIMINGS.has("whenever")).toBe(false);
  });

  it("MEAL_TIMING_OPTIONS is before/after food", () => {
    expect(MEAL_TIMING_OPTIONS.map((o) => o.value)).toEqual(["before_food", "after_food"]);
  });
});
