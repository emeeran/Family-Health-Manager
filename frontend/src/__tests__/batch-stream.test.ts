import {
  createBatchAccumulator,
  applyBatchStreamEvent,
  finalizeBatch,
  makeErrorItem,
} from "@/lib/batch-stream";
import type { BatchExtractionItem } from "@/lib/types/health-record";

/** Build a successful extraction item so tests have a stable payload to place. */
function success(filename: string): BatchExtractionItem {
  return {
    filename,
    staging_file_id: `${filename}.staged`,
    extracted: {
      record_type: "doctor_visit",
      record_date: "2024-01-15",
      diagnosis: filename,
    } as BatchExtractionItem["extracted"],
    transcription: null,
    is_duplicate: false,
    duplicate_of_id: null,
    duplicate_of_diagnosis: null,
    error: null,
    verification: null,
  };
}

describe("createBatchAccumulator", () => {
  it("pre-sizes the result array and starts at zero completed", () => {
    const acc = createBatchAccumulator(4);
    expect(acc.results).toHaveLength(4);
    expect(acc.results.every((r) => r === null)).toBe(true);
    expect(acc.completed).toBe(0);
  });
});

describe("applyBatchStreamEvent", () => {
  it("places each file_complete at its upload-order index, regardless of arrival order", () => {
    const acc = createBatchAccumulator(4);
    // Simulate completion out of order (index 2, 0, 3, 1).
    applyBatchStreamEvent(acc, 0, {
      stage: "file_complete",
      index: 2,
      total: 4,
      item: success("c.pdf"),
    });
    applyBatchStreamEvent(acc, 0, {
      stage: "file_complete",
      index: 0,
      total: 4,
      item: success("a.pdf"),
    });
    applyBatchStreamEvent(acc, 0, {
      stage: "file_complete",
      index: 3,
      total: 4,
      item: success("d.pdf"),
    });
    applyBatchStreamEvent(acc, 0, {
      stage: "file_complete",
      index: 1,
      total: 4,
      item: success("b.pdf"),
    });

    expect(acc.completed).toBe(4);
    expect(finalizeBatch(acc, ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]).map((i) => i.filename)).toEqual(
      ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]
    );
  });

  it("shifts per-chunk indices by chunkOffset across multiple chunks", () => {
    // Two chunks of 3 + 2 files. Chunk 2's local index 0 is global index 3.
    const acc = createBatchAccumulator(5);
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 1, item: success("a1") });
    applyBatchStreamEvent(acc, 3, { stage: "file_complete", index: 0, item: success("b0") });
    applyBatchStreamEvent(acc, 3, { stage: "file_complete", index: 1, item: success("b1") });
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 0, item: success("a0") });
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 2, item: success("a2") });

    const ordered = finalizeBatch(acc, ["a0", "a1", "a2", "b0", "b1"]);
    expect(ordered.map((i) => i.filename)).toEqual(["a0", "a1", "a2", "b0", "b1"]);
  });

  it("ignores non-file_complete events (start/done/keepalive) and duplicates", () => {
    const acc = createBatchAccumulator(2);
    applyBatchStreamEvent(acc, 0, { stage: "start", total: 2 });
    applyBatchStreamEvent(acc, 0, { stage: "done", total: 2 });
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 0, item: success("a") });
    // Late duplicate for the same slot must not double-count or overwrite.
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 0, item: success("a-late") });
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 1, item: success("b") });

    expect(acc.completed).toBe(2);
    expect(finalizeBatch(acc, ["a", "b"])[0].filename).toBe("a"); // original kept, not "a-late"
  });

  it("ignores out-of-range indices defensively", () => {
    const acc = createBatchAccumulator(1);
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 5, item: success("x") });
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: -1, item: success("y") });
    expect(acc.completed).toBe(0);
  });
});

describe("finalizeBatch + makeErrorItem", () => {
  it("fills unfilled slots with error items so no null leaks to the review UI", () => {
    const acc = createBatchAccumulator(3);
    applyBatchStreamEvent(acc, 0, { stage: "file_complete", index: 1, item: success("b") });

    const out = finalizeBatch(acc, ["a.pdf", "b.pdf", "c.pdf"]);
    expect(out).toHaveLength(3);
    expect(out[1].filename).toBe("b");
    expect(out[0].error).toBeTruthy();
    expect(out[2].error).toBeTruthy();
    expect(out[0].filename).toBe("a.pdf");
  });

  it("makeErrorItem has the full BatchExtractionItem shape with null extracted", () => {
    const item = makeErrorItem("scan.pdf", "boom");
    expect(item).toMatchObject({
      filename: "scan.pdf",
      staging_file_id: null,
      extracted: null,
      transcription: null,
      is_duplicate: false,
      duplicate_of_id: null,
      duplicate_of_diagnosis: null,
      verification: null,
      error: "boom",
    });
  });
});
