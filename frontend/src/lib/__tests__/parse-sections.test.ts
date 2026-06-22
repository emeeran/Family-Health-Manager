import { describe, it, expect } from "vitest";
import { parseSections, sectionKey } from "../parse-sections";

describe("parseSections", () => {
  it("parses the model's actual '**N. Title**' format (stars wrap the number)", () => {
    const md =
      "**1. Health Overview**\n\nMeeran is a 59-year-old male.\n\n**2. Active Conditions**\n\nT2DM is poorly controlled.";
    const out = parseSections(md);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({
      title: "Health Overview",
      body: "Meeran is a 59-year-old male.",
      key: "overview",
    });
    expect(out[1]).toMatchObject({
      title: "Active Conditions",
      body: "T2DM is poorly controlled.",
      key: "conditions",
    });
  });

  it("parses the prompt's 'N. **Title**' format", () => {
    const md = "1. **Health Overview**\nBody A\n\n2. **Lab Trends**\nBody B";
    const out = parseSections(md);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ title: "Health Overview", key: "overview" });
    expect(out[1]).toMatchObject({ title: "Lab Trends", key: "labs" });
  });

  it("parses markdown '### Title' headings", () => {
    const md = "### Health Overview\nBody A\n### Risk Assessment\nBody B";
    const out = parseSections(md);
    expect(out).toHaveLength(2);
    expect(out[1]).toMatchObject({ title: "Risk Assessment", key: "risk" });
  });

  it("parses a full 6-section payload and maps every key", () => {
    const md = [
      "**1. Health Overview**",
      "overview body",
      "**2. Active Conditions**",
      "conditions body",
      "**3. Lab Trends**",
      "labs body",
      "**4. Risk Assessment**",
      "risk body",
      "**5. Recommendations**",
      "recs body",
      "**6. Follow-up Actions**",
      "followup body",
    ].join("\n\n");
    const out = parseSections(md);
    expect(out.map((s) => s.key)).toEqual([
      "overview",
      "conditions",
      "labs",
      "risk",
      "recommendations",
      "follow_up",
    ]);
    expect(out.every((s) => s.body.length > 0)).toBe(true);
  });

  it("does not false-split on bold sub-items that start a line", () => {
    const md =
      "**1. Active Conditions**\n\n**Parkinson's Disease**: stable.\n\n**T2DM**: worsening.";
    const out = parseSections(md);
    expect(out).toHaveLength(1);
    expect(out[0].title).toBe("Active Conditions");
    expect(out[0].body).toContain("Parkinson's Disease");
    expect(out[0].body).toContain("T2DM");
  });

  it("falls back to a single 'Health Insights' section when there are no headings", () => {
    const out = parseSections("Just a paragraph with no headings.");
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ title: "Health Insights", key: "other" });
  });

  it("returns [] for empty/whitespace input", () => {
    expect(parseSections("")).toEqual([]);
    expect(parseSections("   \n\n  ")).toEqual([]);
  });
});

describe("sectionKey", () => {
  it("maps titles to stable keys", () => {
    expect(sectionKey("Health Overview")).toBe("overview");
    expect(sectionKey("Active Conditions")).toBe("conditions");
    expect(sectionKey("Lab Trends")).toBe("labs");
    expect(sectionKey("Risk Assessment")).toBe("risk");
    expect(sectionKey("Recommendations")).toBe("recommendations");
    expect(sectionKey("Follow-up Actions")).toBe("follow_up");
    expect(sectionKey("Something Else")).toBe("other");
  });
});
