import { parsePastedRows } from "@/components/records/dynamic-table";

const LAB_FIELDS = [{ key: "test_name" }, { key: "result" }, { key: "ref_value" }, { key: "note" }];

describe("parsePastedRows (#22 bulk import)", () => {
  it("maps tab-separated columns onto fields in order", () => {
    const rows = parsePastedRows("HbA1c\t7.8\t<6.0%\tHigh\nGlucose\t142\t70-100", LAB_FIELDS);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      test_name: "HbA1c",
      result: "7.8",
      ref_value: "<6.0%",
      note: "High",
    });
    expect(rows[1]).toEqual({ test_name: "Glucose", result: "142", ref_value: "70-100", note: "" });
  });

  it("splits on comma, pipe, and multiple spaces too", () => {
    expect(parsePastedRows("HbA1c, 7.8, <6.0%", LAB_FIELDS)[0].result).toBe("7.8");
    expect(parsePastedRows("HbA1c | 7.8 | <6.0%", LAB_FIELDS)[0].ref_value).toBe("<6.0%");
    expect(parsePastedRows("HbA1c   7.8   <6.0%", LAB_FIELDS)[0].test_name).toBe("HbA1c");
  });

  it("skips blank / whitespace-only lines", () => {
    const rows = parsePastedRows("\nHbA1c\t7.8\n\n   \n  \t  ", LAB_FIELDS);
    expect(rows).toHaveLength(1);
    expect(rows[0].test_name).toBe("HbA1c");
  });

  it("returns nothing for empty input", () => {
    expect(parsePastedRows("", LAB_FIELDS)).toEqual([]);
    expect(parsePastedRows("   \n\n", LAB_FIELDS)).toEqual([]);
  });
});
