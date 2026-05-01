import type { RecordType } from "./types/enums";
import type { RecordTypeConfig } from "./record-type-configs";
import { getConfig, getTables } from "./record-type-configs";

const STRUCTURED_MARKER = "_type";
const STRUCTURED_VERSION = 1;

/** Remove "--- From filename.pdf ---" markers from extracted text. */
function cleanSourceFileMarkers(text: string): string {
  return text.replace(/\n*--- From [^\n]+ ---\n*/g, "\n").replace(/^\n+|\n+$/g, "");
}

export interface DeserializedData {
  isStructured: boolean;
  fields: Record<string, string>;
  /** Legacy single-table (for backward compat with old records) */
  tableRows: Record<string, string>[];
  /** Multi-table data keyed by table key */
  tableData: Record<string, Record<string, string>[]>;
  notes: string;
}

/**
 * Serialize custom fields + table data + notes into clinical_data JSON.
 * Supports both single-table (legacy) and multi-table configs.
 */
export function serializeClinicalData(
  recordType: RecordType,
  customFields: Record<string, string>,
  tableData: Record<string, Record<string, string>[]>,
  notes?: string
): string {
  const config = getConfig(recordType);
  const tables = getTables(config);

  // Types with no custom fields and no tables (misc_record) use plain text
  if (config.customFields.length === 0 && tables.length === 0) {
    return notes || customFields.clinical_data || "";
  }

  const payload: Record<string, unknown> = {
    [STRUCTURED_MARKER]: "structured",
    _version: STRUCTURED_VERSION,
    _recordType: recordType,
  };

  // Add non-empty custom field values
  for (const fieldDef of config.customFields) {
    const val = customFields[fieldDef.key];
    if (val !== undefined && val !== "") {
      payload[fieldDef.key] = val;
    }
  }

  // Add table rows for each table definition
  for (const tableDef of tables) {
    const rows = tableData[tableDef.key];
    if (rows && rows.length > 0) {
      const nonEmptyRows = rows.filter((row) =>
        Object.values(row).some((v) => v !== undefined && v !== "")
      );
      if (nonEmptyRows.length > 0) {
        payload[tableDef.key] = nonEmptyRows;
      }
    }
  }

  if (notes) {
    payload._notes = notes;
  }

  return JSON.stringify(payload);
}

/**
 * Deserialize clinical_data back into fields + table data + notes.
 */
export function deserializeClinicalData(raw: string): DeserializedData {
  if (!raw) {
    return { isStructured: false, fields: {}, tableRows: [], tableData: {}, notes: "" };
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed[STRUCTURED_MARKER] !== "structured") {
      return {
        isStructured: false,
        fields: { clinical_data: cleanSourceFileMarkers(raw) },
        tableRows: [],
        tableData: {},
        notes: "",
      };
    }

    const fields: Record<string, string> = {};
    const tableData: Record<string, Record<string, string>[]> = {};
    let legacyTableRows: Record<string, string>[] = [];
    let legacyTableKey = "";

    const recordType = parsed._recordType as RecordType;
    const config = getConfig(recordType);
    const tableDefs = getTables(config);
    const tableKeys = new Set(tableDefs.map((t) => t.key));

    for (const [key, value] of Object.entries(parsed)) {
      if (key.startsWith("_")) continue;
      if (Array.isArray(value)) {
        const arr = value as Record<string, string>[];
        if (tableKeys.has(key)) {
          tableData[key] = arr;
        }
        // Keep first array found as legacy tableRows for backward compat
        if (!legacyTableKey) {
          legacyTableKey = key;
          legacyTableRows = arr;
        }
      } else {
        fields[key] = String(value);
      }
    }

    return {
      isStructured: true,
      fields,
      tableRows: legacyTableRows,
      tableData,
      notes: typeof parsed._notes === "string" ? cleanSourceFileMarkers(parsed._notes) : "",
    };
  } catch {
    return {
      isStructured: false,
      fields: { clinical_data: raw },
      tableRows: [],
      tableData: {},
      notes: "",
    };
  }
}

export function isStructuredClinicalData(raw: string): boolean {
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw);
    return parsed[STRUCTURED_MARKER] === "structured";
  } catch {
    return false;
  }
}

export function getDefaultCustomFields(config: RecordTypeConfig): Record<string, string> {
  const defaults: Record<string, string> = {};
  for (const field of config.customFields) {
    defaults[field.key] = "";
  }
  return defaults;
}

export function getDefaultTableData(
  config: RecordTypeConfig
): Record<string, Record<string, string>[]> {
  const tables = getTables(config);
  const data: Record<string, Record<string, string>[]> = {};
  for (const tableDef of tables) {
    const row: Record<string, string> = {};
    for (const field of tableDef.fields) {
      row[field.key] = "";
    }
    data[tableDef.key] = [row];
  }
  return data;
}

/** Legacy helper — returns rows for first table only */
export function getDefaultTableRows(config: RecordTypeConfig): Record<string, string>[] {
  const data = getDefaultTableData(config);
  const keys = Object.keys(data);
  return keys.length > 0 ? data[keys[0]] : [];
}
