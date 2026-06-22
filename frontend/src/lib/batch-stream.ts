/**
 * Pure helpers for the streaming batch extraction flow
 * (`/records/extract-batch/stream`). Kept separate from the React component so
 * the event-accumulation logic is unit-testable with synthetic SSE feeds.
 *
 * The backend emits one `file_complete` event per file in *completion* order;
 * each carries the file's 0-based `index` within its chunk. We place results
 * into a pre-sized array at their upload-order slot so the review UI stays
 * stable regardless of which file finishes first.
 */

import type { BatchExtractionItem } from "@/lib/types/health-record";

export interface BatchStreamEvent {
  stage?: string;
  index?: number;
  total?: number;
  item?: BatchExtractionItem;
  message?: string;
}

export interface BatchAccumulator {
  /** Pre-sized to the total file count; `null` until a file completes. */
  results: (BatchExtractionItem | null)[];
  completed: number;
}

export function createBatchAccumulator(total: number): BatchAccumulator {
  return { results: new Array(total).fill(null), completed: 0 };
}

/**
 * Place a streaming event into the accumulator at its upload-order slot.
 *
 * @param chunkOffset Shifts the event's per-chunk `index` into the global array
 *   (one stream runs per chunk; chunk N's indices are local to that chunk).
 * Idempotent against duplicate/late events: a slot is filled only once.
 */
export function applyBatchStreamEvent(
  acc: BatchAccumulator,
  chunkOffset: number,
  event: BatchStreamEvent
): void {
  if (event.stage === "file_complete" && typeof event.index === "number" && event.item) {
    const idx = chunkOffset + event.index;
    if (idx >= 0 && idx < acc.results.length && acc.results[idx] === null) {
      acc.results[idx] = event.item;
      acc.completed += 1;
    }
  }
}

export function makeErrorItem(filename: string, message: string): BatchExtractionItem {
  return {
    filename,
    staging_file_id: null,
    extracted: null,
    transcription: null,
    is_duplicate: false,
    duplicate_of_id: null,
    duplicate_of_diagnosis: null,
    error: message,
    verification: null,
  };
}

/**
 * Materialize the final `BatchExtractionItem[]`, filling any unfilled slots
 * (aborted chunk / missed event) with error items so the review/auto-save paths
 * never observe a `null`.
 */
export function finalizeBatch(
  acc: BatchAccumulator,
  fallbackNames: string[]
): BatchExtractionItem[] {
  return acc.results.map(
    (r, i) => r ?? makeErrorItem(fallbackNames[i] ?? `file ${i + 1}`, "Extraction incomplete")
  );
}
