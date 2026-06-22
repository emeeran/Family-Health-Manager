/**
 * Transient, in-memory handoff for launching the record wizard from an external
 * "smart" surface (SmartEntryBar, smart-entry page). Carries a text snippet and/or
 * a File that the wizard consumes on mount, so those surfaces become thin launchers
 * instead of reimplementing parse + save.
 *
 * Module-level (not sessionStorage): Files are not serializable. The entry is
 * consumed once on wizard mount and cleared, so it never persists across reloads.
 */
interface PendingEntry {
  text?: string;
  file?: File;
}

let pending: PendingEntry | null = null;

export function setPendingEntry(entry: PendingEntry): void {
  pending = entry;
}

/** Read and clear the pending entry (call once on wizard mount). */
export function consumePendingEntry(): PendingEntry | null {
  const entry = pending;
  pending = null;
  return entry;
}

/** Read without clearing (for guards / link enabling). */
export function peekPendingEntry(): PendingEntry | null {
  return pending;
}
