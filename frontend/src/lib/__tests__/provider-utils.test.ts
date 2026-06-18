import { describe, it, expect } from "vitest";
import { stripProviderTitle, sortedProviders } from "../provider-utils";

describe("stripProviderTitle", () => {
  it("strips 'Dr.' with a space", () => {
    expect(stripProviderTitle("Dr. Smith")).toBe("Smith");
  });

  it("strips 'Dr' without a period", () => {
    expect(stripProviderTitle("Dr Smith")).toBe("Smith");
  });

  it("is case-insensitive", () => {
    expect(stripProviderTitle("DR. Jane Smith")).toBe("Jane Smith");
    expect(stripProviderTitle("dr smith")).toBe("smith");
  });

  it("preserves names that merely start with 'dr'", () => {
    expect(stripProviderTitle("Dryden")).toBe("Dryden");
    expect(stripProviderTitle("Drake")).toBe("Drake");
  });

  it("handles null/undefined/empty", () => {
    expect(stripProviderTitle(null)).toBe("");
    expect(stripProviderTitle(undefined)).toBe("");
    expect(stripProviderTitle("")).toBe("");
  });

  it("leaves names without a title untouched", () => {
    expect(stripProviderTitle("City Lab")).toBe("City Lab");
  });
});

describe("sortedProviders", () => {
  it("sorts by surname after stripping the title, case-insensitively", () => {
    const providers = [
      { id: "1", name: "Dr. Smith" },
      { id: "2", name: "dr adams" },
      { id: "3", name: "Dr. Brown" },
    ];
    expect(sortedProviders(providers).map((p) => p.name)).toEqual([
      "dr adams",
      "Dr. Brown",
      "Dr. Smith",
    ]);
  });

  it("does not mutate the input array", () => {
    const providers = [
      { id: "1", name: "Dr. Zeta" },
      { id: "2", name: "Dr. Alpha" },
    ];
    sortedProviders(providers);
    expect(providers.map((p) => p.name)).toEqual(["Dr. Zeta", "Dr. Alpha"]);
  });

  it("returns an empty array unchanged", () => {
    expect(sortedProviders([])).toEqual([]);
  });
});
