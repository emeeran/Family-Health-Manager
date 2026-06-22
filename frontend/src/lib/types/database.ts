// Database integrity check + repair (Settings → Data tab)

export type RepairOperation = "checkpoint" | "reindex" | "vacuum";

export interface TableCount {
  name: string;
  count: number;
  error?: string | null;
}

export interface DatabaseStats {
  engine: "sqlite" | "postgresql";
  database_bytes: number;
  wal_bytes?: number | null;
  shm_bytes?: number | null;
  page_size?: number | null;
  page_count?: number | null;
  freelist_pages?: number | null;
  journal_mode?: string | null;
}

export interface IntegrityReport {
  /** Structural integrity only (integrity_check + quick_check). FK excluded. */
  ok: boolean;
  engine: "sqlite" | "postgresql";
  integrity_check: string[];
  quick_check: string[];
  foreign_key_violations: number;
  foreign_key_note?: string | null;
  tables: TableCount[];
  stats: DatabaseStats;
  duration_ms: number;
  timed_out: boolean;
  notes: string[];
}

export interface StatsSnapshot {
  database_bytes: number;
  freelist_pages?: number | null;
  wal_bytes?: number | null;
}

export interface RepairResponse {
  ok: boolean;
  operation: RepairOperation;
  message: string;
  before?: StatsSnapshot | null;
  after?: StatsSnapshot | null;
  duration_ms: number;
  notes: string[];
}
