import { describe, it, expect } from "vitest";
import {
  splitBlocks,
  detectTrajectory,
  detectSeverity,
  detectPriority,
  detectLabDeltas,
  deriveRiskLevel,
  deriveKpis,
} from "../insight-extract";
import type { InsightSection } from "../parse-sections";

function section(key: string, body: string): InsightSection {
  return { title: key, body, key };
}

describe("splitBlocks", () => {
  it("splits on blank lines and trims/drops empties", () => {
    const body = "First condition.\n\nSecond condition.\n\n\n  Third condition.  ";
    expect(splitBlocks(body)).toEqual([
      "First condition.",
      "Second condition.",
      "Third condition.",
    ]);
  });

  it("returns a single block when there are no blank-line separators", () => {
    expect(splitBlocks("One line only")).toEqual(["One line only"]);
  });

  it("returns [] for empty/whitespace input", () => {
    expect(splitBlocks("")).toEqual([]);
    expect(splitBlocks("   \n\n  \n")).toEqual([]);
  });
});

describe("detectTrajectory", () => {
  it("flags worsening / suboptimally controlled as 'Needs attention' (bad)", () => {
    expect(detectTrajectory("T2DM, currently suboptimally controlled — HbA1c 8.9%")).toEqual({
      label: "Needs attention",
      dir: "down",
      tone: "bad",
    });
    expect(detectTrajectory("Blood pressure is worsening despite therapy")).toEqual({
      label: "Needs attention",
      dir: "down",
      tone: "bad",
    });
  });

  it("does not read 'uncontrolled' as 'controlled' (good)", () => {
    expect(detectTrajectory("Asthma uncontrolled this quarter")?.tone).toBe("bad");
  });

  it("flags improving / well controlled as 'Improving' (good)", () => {
    expect(detectTrajectory("Cholesterol improving on statin therapy")).toEqual({
      label: "Improving",
      dir: "up",
      tone: "good",
    });
    expect(detectTrajectory("Hypertension well controlled on current meds")?.tone).toBe("good");
  });

  it("flags stable as 'Stable' (warn)", () => {
    expect(detectTrajectory("Renal function stable since last visit")).toEqual({
      label: "Stable",
      dir: "flat",
      tone: "warn",
    });
  });

  it("returns null when no trajectory cue is present", () => {
    expect(detectTrajectory("The patient lives in a city.")).toBeNull();
    expect(detectTrajectory("")).toBeNull();
  });

  it("ignores markdown bold markers", () => {
    expect(detectTrajectory("**HbA1c** deteriorated from 7.2 to 8.9")?.tone).toBe("bad");
  });
});

describe("detectSeverity", () => {
  it("detects high severity", () => {
    expect(detectSeverity("Critical cardiovascular risk")).toBe("high");
    expect(detectSeverity("Severe anaemia")).toBe("high");
  });

  it("detects moderate severity", () => {
    expect(detectSeverity("Elevated cardiovascular risk")).toBe("moderate");
    expect(detectSeverity("Borderline cholesterol")).toBe("moderate");
  });

  it("detects low severity (narrow set — no bare 'low')", () => {
    expect(detectSeverity("Mild elevation noted")).toBe("low");
  });

  it("does not misread 'low hemoglobin' as low severity", () => {
    expect(detectSeverity("Low hemoglobin of 7.8")).toBeNull();
  });

  it("returns null when no severity cue is present", () => {
    expect(detectSeverity("The patient is 52 years old.")).toBeNull();
    expect(detectSeverity("")).toBeNull();
  });
});

describe("detectPriority", () => {
  it("detects urgent", () => {
    expect(detectPriority("Review HbA1c urgently within 2 weeks")).toBe("urgent");
  });

  it("detects important", () => {
    expect(detectPriority("Discuss dose escalation with endocrinologist")).toBe("important");
  });

  it("detects routine", () => {
    expect(detectPriority("Continue annual monitoring")).toBe("routine");
  });

  it("returns null when no priority cue is present", () => {
    expect(detectPriority("The sky is blue.")).toBeNull();
    expect(detectPriority("")).toBeNull();
  });
});

describe("detectLabDeltas", () => {
  it("parses a 'from X to Y' delta with units and bold markers", () => {
    const out = detectLabDeltas(
      "Fasting glucose rose from **110 mg/dL** to **142 mg/dL**, crossing ranges."
    );
    expect(out).toHaveLength(1);
    expect(out[0]).toEqual({ from: "110", to: "142", unit: "mg/dL", dir: "up" });
  });

  it("computes dir as down when the value decreased", () => {
    const out = detectLabDeltas("Hemoglobin improved from 8.9 to 10.2 gm%");
    expect(out[0]).toMatchObject({ from: "8.9", to: "10.2", dir: "up" });
    const down = detectLabDeltas("LDL fell from 160 to 120 mg/dL");
    expect(down[0].dir).toBe("down");
  });

  it("tolerates a parenthetical date between the two values", () => {
    const out = detectLabDeltas("rose from **7.2%** (Jan) to **8.9%** (Mar)");
    expect(out[0]).toEqual({ from: "7.2", to: "8.9", unit: "%", dir: "up" });
  });

  it("returns [] when no delta pattern is present", () => {
    expect(detectLabDeltas("HbA1c is 8.9% which is above target.")).toEqual([]);
    expect(detectLabDeltas("")).toEqual([]);
  });
});

describe("deriveRiskLevel", () => {
  it("returns the strongest severity across risk + conditions sections", () => {
    const sections = [
      section("conditions", "T2DM is mild and improving."),
      section("risk", "Elevated cardiovascular risk noted."),
    ];
    expect(deriveRiskLevel(sections)).toBe("moderate");
  });

  it("high beats moderate", () => {
    const sections = [
      section("risk", "Moderate lipid risk."),
      section("conditions", "Critical kidney decline."),
    ];
    expect(deriveRiskLevel(sections)).toBe("high");
  });

  it("returns null when no severity cue is detectable (no false 'Low')", () => {
    const sections = [
      section("risk", "The patient has several medications."),
      section("conditions", "No major changes this quarter."),
    ];
    expect(deriveRiskLevel(sections)).toBeNull();
  });

  it("ignores non-risk sections", () => {
    const sections = [
      section("overview", "This is a severe case."), // should NOT count
      section("labs", "values look fine"),
    ];
    expect(deriveRiskLevel(sections)).toBeNull();
  });
});

describe("deriveKpis", () => {
  it("counts paragraph blocks per section key", () => {
    const sections = [
      section("overview", "Overview prose."),
      section("conditions", "T2DM.\n\nHypertension.\n\nAsthma."),
      section("labs", "HbA1c.\n\nLDL."),
      section("risk", "CV risk.\n\nRenal risk."),
      section("follow_up", "Review in 2 weeks.\n\nRepeat labs."),
    ];
    expect(deriveKpis(sections)).toEqual({
      conditions: 3,
      labs: 2,
      risks: 2,
      followUps: 2,
    });
  });

  it("returns 0 for absent sections", () => {
    expect(deriveKpis([section("overview", "only overview")])).toEqual({
      conditions: 0,
      labs: 0,
      risks: 0,
      followUps: 0,
    });
  });

  it("returns all-zero for empty input", () => {
    expect(deriveKpis([])).toEqual({ conditions: 0, labs: 0, risks: 0, followUps: 0 });
  });
});
