/**
 * Batching constraints for the `/extract-batch` endpoint. Each chunk is sent as
 * its own request, so every chunk must satisfy BOTH limits the backend enforces.
 */

/** Max bytes per request — matches the server request-body limit. */
export const MAX_BATCH_BYTES = 90 * 1024 * 1024; // 90 MB

/**
 * Max files per request — matches the hard cap in
 * `health_records.extract_batch` (>20 → HTTP 400 "Maximum 20 files per batch").
 */
export const MAX_BATCH_FILES = 20;

interface Batchable {
  size: number;
}

/**
 * Split a list of files into chunks that each satisfy BOTH backend constraints:
 * at most {@link MAX_BATCH_FILES} files AND at most {@link MAX_BATCH_BYTES} of
 * total size.
 *
 * Each chunk becomes one `/extract-batch` request. Splitting on the count cap
 * (not just size) is what lets bulk uploads of many small files work: without
 * it, a folder of e.g. 43 small PDFs under 90MB lands in a single chunk that the
 * backend rejects wholesale with "Maximum 20 files per batch".
 *
 * A file larger than {@link MAX_BATCH_BYTES} still gets its own chunk (it is
 * never dropped); the size guard only flushes a non-empty chunk.
 */
export function chunkFilesForBatch<T extends Batchable>(files: T[]): T[][] {
  const chunks: T[][] = [];
  let current: T[] = [];
  let currentSize = 0;

  for (const f of files) {
    const overSize = currentSize + f.size > MAX_BATCH_BYTES && current.length > 0;
    const overCount = current.length >= MAX_BATCH_FILES;
    if (overSize || overCount) {
      chunks.push(current);
      current = [];
      currentSize = 0;
    }
    current.push(f);
    currentSize += f.size;
  }
  if (current.length > 0) chunks.push(current);
  return chunks;
}
