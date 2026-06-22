import { chunkFilesForBatch, MAX_BATCH_BYTES, MAX_BATCH_FILES } from "@/lib/batch-chunks";

interface FakeFile {
  size: number;
  name: string;
}

/** Build a lightweight file stub — only `.size` matters to the chunker. */
function file(size: number, name = `f${size}.pdf`): FakeFile {
  return { size, name };
}

describe("chunkFilesForBatch", () => {
  it("returns no chunks for empty input", () => {
    expect(chunkFilesForBatch([])).toEqual([]);
  });

  it("keeps a few small files in a single chunk", () => {
    const files = [file(1_000), file(2_000), file(3_000)];
    expect(chunkFilesForBatch(files)).toEqual([files]);
  });

  it("keeps exactly MAX_BATCH_FILES files in one chunk (boundary)", () => {
    const files = Array.from({ length: MAX_BATCH_FILES }, () => file(1_000));
    const chunks = chunkFilesForBatch(files);
    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toHaveLength(MAX_BATCH_FILES);
  });

  it("splits at MAX_BATCH_FILES — the 43-file bulk-upload regression", () => {
    // 43 small PDFs together are far under 90MB, so without the count cap they
    // would all land in one chunk and the backend would reject them.
    const files = Array.from({ length: 43 }, (_, i) => file(2 * 1024 * 1024, `doc${i}.pdf`));

    const chunks = chunkFilesForBatch(files);

    // 43 → [20, 20, 3]
    expect(chunks.map((c) => c.length)).toEqual([20, 20, 3]);
    // No chunk may exceed the file-count cap
    for (const c of chunks) expect(c.length).toBeLessThanOrEqual(MAX_BATCH_FILES);
    // No chunk may exceed the byte cap
    for (const c of chunks) {
      const total = c.reduce((sum, f) => sum + f.size, 0);
      expect(total).toBeLessThanOrEqual(MAX_BATCH_BYTES);
    }
  });

  it("puts one file beyond the cap into its own small chunk", () => {
    const files = Array.from({ length: MAX_BATCH_FILES + 1 }, () => file(1_000));
    const chunks = chunkFilesForBatch(files);
    expect(chunks.map((c) => c.length)).toEqual([MAX_BATCH_FILES, 1]);
  });

  it("splits on the byte cap when few files are huge", () => {
    // Two 50MB files = 100MB > 90MB, so they can't share a chunk.
    const files = [file(50 * 1024 * 1024), file(50 * 1024 * 1024)];
    const chunks = chunkFilesForBatch(files);
    expect(chunks).toHaveLength(2);
    expect(chunks[0]).toHaveLength(1);
    expect(chunks[1]).toHaveLength(1);
  });

  it("still emits a chunk for a single file larger than the byte cap", () => {
    // An oversized lone file is not dropped — it becomes its own chunk.
    const oversized = file(150 * 1024 * 1024);
    expect(chunkFilesForBatch([oversized])).toEqual([[oversized]]);
  });

  it("preserves all files and their order", () => {
    const files = Array.from({ length: 53 }, (_, i) => file(i + 1, `n${i}`));
    const chunks = chunkFilesForBatch(files);

    const flattened = chunks.flat();
    expect(flattened).toHaveLength(files.length);
    expect(flattened).toEqual(files);
  });
});
