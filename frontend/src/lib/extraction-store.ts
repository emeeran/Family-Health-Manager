/**
 * Persist extracted structured data in sessionStorage so it survives
 * navigation between "new record" pages for the same member.
 *
 * Each document upload creates a separate "batch" (up to 3 stored).
 * Auto-fill lets the user pick which batch to apply.
 */

export interface ExtractionBatch {
  id: string;
  fileName: string;
  timestamp: number;
  transcription: string | null;
  prescriptions: Record<string, string>[];
  labTests: Record<string, string>[];
  eyeglass: Record<string, string> | null;
  baseFields: {
    record_type?: string;
    record_date?: string;
    record_time?: string;
    provider_name?: string;
    diagnosis?: string;
    next_review_date?: string;
    chief_complaint?: string;
    existing_conditions?: string;
    investigations?: string;
  };
}

export interface StoredExtractions {
  batches: ExtractionBatch[];
}

const MAX_BATCHES = 3;

function storageKey(memberId: string) {
  return `health-extraction-${memberId}`;
}

function loadAll(memberId: string): StoredExtractions {
  try {
    const raw = sessionStorage.getItem(storageKey(memberId));
    if (!raw) return { batches: [] };

    const parsed = JSON.parse(raw);

    // New format: { batches: [...] }
    if (parsed.batches && Array.isArray(parsed.batches)) {
      return parsed as StoredExtractions;
    }

    // Legacy format: flat object with prescriptions/labTests/eyeglass
    // Migrate into a single batch
    if (parsed.prescriptions?.length || parsed.labTests?.length || parsed.eyeglass) {
      const migrated: StoredExtractions = {
        batches: [
          {
            id: `legacy-${Date.now()}`,
            fileName: "Previous extraction",
            timestamp: Date.now(),
            transcription: null,
            prescriptions: parsed.prescriptions || [],
            labTests: parsed.labTests || [],
            eyeglass: parsed.eyeglass || null,
            baseFields: parsed.baseFields || {},
          },
        ],
      };
      sessionStorage.setItem(storageKey(memberId), JSON.stringify(migrated));
      return migrated;
    }

    return { batches: [] };
  } catch {
    return { batches: [] };
  }
}

function saveAll(memberId: string, data: StoredExtractions) {
  if (data.batches.length === 0) {
    sessionStorage.removeItem(storageKey(memberId));
    return;
  }
  try {
    sessionStorage.setItem(storageKey(memberId), JSON.stringify(data));
  } catch {
    // sessionStorage full or unavailable
  }
}

/** Save a new extraction batch (from a file upload). Keeps only the last 3. */
export function saveExtraction(memberId: string, batch: Omit<ExtractionBatch, "id" | "timestamp">) {
  const data = loadAll(memberId);

  const newBatch: ExtractionBatch = {
    ...batch,
    id: `ext-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: Date.now(),
  };

  data.batches.unshift(newBatch);
  data.batches = data.batches.slice(0, MAX_BATCHES);

  saveAll(memberId, data);
}

/** Get all stored batches. */
export function loadExtraction(memberId: string): StoredExtractions | null {
  const data = loadAll(memberId);
  return data.batches.length > 0 ? data : null;
}

/** Get batches that contain data for a specific type. */
export function getBatchesForType(
  memberId: string,
  type: "prescriptions" | "labTests" | "eyeglass"
): ExtractionBatch[] {
  const data = loadAll(memberId);
  return data.batches.filter((b) => {
    if (type === "prescriptions") return b.prescriptions.length > 0;
    if (type === "labTests") return b.labTests.length > 0;
    return b.eyeglass !== null;
  });
}

/** Remove a specific batch by ID. */
export function removeBatch(memberId: string, batchId: string) {
  const data = loadAll(memberId);
  data.batches = data.batches.filter((b) => b.id !== batchId);
  saveAll(memberId, data);
}

/** Consume (extract + remove) data from a specific batch. Returns the data or null. */
export function consumeBatch(
  memberId: string,
  batchId: string,
  type: "prescriptions" | "labTests" | "eyeglass"
): Record<string, string>[] | Record<string, string> | null {
  const data = loadAll(memberId);
  const batch = data.batches.find((b) => b.id === batchId);
  if (!batch) return null;

  let result: Record<string, string>[] | Record<string, string> | null = null;

  if (type === "prescriptions" && batch.prescriptions.length > 0) {
    result = batch.prescriptions;
    batch.prescriptions = [];
  } else if (type === "labTests" && batch.labTests.length > 0) {
    result = batch.labTests;
    batch.labTests = [];
  } else if (type === "eyeglass" && batch.eyeglass) {
    result = batch.eyeglass;
    batch.eyeglass = null;
  }

  // Remove batch if now empty
  const isEmpty =
    batch.prescriptions.length === 0 && batch.labTests.length === 0 && !batch.eyeglass;
  if (isEmpty) {
    data.batches = data.batches.filter((b) => b.id !== batchId);
  }

  saveAll(memberId, data);
  return result;
}

/** Clear all stored extraction data for a member. */
export function clearExtraction(memberId: string) {
  sessionStorage.removeItem(storageKey(memberId));
}
