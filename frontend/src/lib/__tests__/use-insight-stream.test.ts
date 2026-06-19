import { describe, it, expect } from "vitest";
import { applyStreamEvent } from "../hooks/use-insight-stream";
import type { StreamState } from "../hooks/use-insight-stream";

const NOW = new Date("2026-06-19T12:00:00Z");
const empty: StreamState = { fullText: "" };

describe("applyStreamEvent", () => {
  it("accumulates tokens across events", () => {
    const a = applyStreamEvent({ stage: "token", content: "Hello " }, empty, NOW);
    expect(a).toEqual({ type: "token", fullText: "Hello " });
    const b = applyStreamEvent({ stage: "token", content: "world" }, { fullText: "Hello " }, NOW);
    expect(b).toEqual({ type: "token", fullText: "Hello world" });
  });

  it("maps the context stage to a label (message or default)", () => {
    expect(applyStreamEvent({ stage: "context", message: "Building context" }, empty, NOW)).toEqual(
      { type: "stage", stage: "Building context" }
    );
    expect(applyStreamEvent({ stage: "context" }, empty, NOW)).toEqual({
      type: "stage",
      stage: "Preparing...",
    });
  });

  it("maps the provider stage to a label", () => {
    expect(applyStreamEvent({ stage: "provider", provider: "Ollama" }, empty, NOW)).toEqual({
      type: "stage",
      stage: "Generating via Ollama...",
    });
  });

  it("builds the insight on complete from accumulated text + event fields", () => {
    const out = applyStreamEvent(
      { stage: "complete", insight_id: "abc", provider: "Ollama" },
      { fullText: "Final report body" },
      NOW
    );
    expect(out).toEqual({
      type: "complete",
      insight: {
        id: "abc",
        response: "Final report body",
        provider_used: "Ollama",
        generated_at: NOW.toISOString(),
        verification: null,
        sections: null,
      },
    });
  });

  it("passes through server-parsed sections on complete", () => {
    const sections = [{ title: "Overview", body: "...", key: "overview" }];
    const out = applyStreamEvent(
      { stage: "complete", insight_id: "x", provider: "p", sections },
      empty,
      NOW
    );
    expect(out.type).toBe("complete");
    if (out.type === "complete") expect(out.insight.sections).toEqual(sections);
  });

  it("maps the error stage to a message (event message or default)", () => {
    expect(applyStreamEvent({ stage: "error", message: "boom" }, empty, NOW)).toEqual({
      type: "error",
      message: "boom",
    });
    expect(applyStreamEvent({ stage: "error" }, empty, NOW)).toEqual({
      type: "error",
      message: "Generation failed",
    });
  });

  it("returns idle for unknown / missing stages", () => {
    expect(applyStreamEvent({ stage: "something-else" }, empty, NOW)).toEqual({ type: "idle" });
    expect(applyStreamEvent({}, empty, NOW)).toEqual({ type: "idle" });
  });
});
