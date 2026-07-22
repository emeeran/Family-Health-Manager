import { describe, expect, it } from "vitest";
import { classifyStage, hasStructuredContent } from "@/lib/streaming-preview-select";

describe("classifyStage", () => {
  it("classifies context/loading/preparing/saving stages", () => {
    expect(classifyStage("Loading patient records...")).toBe("context");
    expect(classifyStage("Preparing...")).toBe("context");
    expect(classifyStage("Saving insight...")).toBe("context");
  });

  it("classifies cloud-provider stages", () => {
    expect(classifyStage("Generating via Cloud AI...")).toBe("cloud");
  });

  it("defaults to local for ollama / unknown stages", () => {
    expect(classifyStage("Generating via Ollama qwen3:4b...")).toBe("local");
    expect(classifyStage("Starting...")).toBe("local");
    expect(classifyStage("")).toBe("local");
  });
});

describe("hasStructuredContent", () => {
  it("is false before any heading is emitted (raw stream / empty)", () => {
    expect(hasStructuredContent("")).toBe(false);
    expect(hasStructuredContent("plain prose with no headings yet")).toBe(false);
  });

  it("is true once a numbered markdown heading has landed", () => {
    const partial = "1. **Health Overview**\nA 45-year-old male with";
    expect(hasStructuredContent(partial)).toBe(true);
  });

  it("is true for multiple sections", () => {
    const md = "1. **Health Overview**\nintro\n\n2. **Active Conditions**\nT2DM";
    expect(hasStructuredContent(md)).toBe(true);
  });
});
