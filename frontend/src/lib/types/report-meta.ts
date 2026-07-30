/**
 * Provenance + freshness metadata for an AI-generated report.
 *
 * `sources` lists the source records (ids/dates/types) that fed the report,
 * computed server-side from real rows (never from LLM output). `freshness_as_of`
 * / `range_start` are the max/min source record dates. All optional — present
 * only on member-level insights (absent for chat / single-record insights).
 */
export interface SourceRef {
  id: string;
  type?: string | null;
  date?: string | null;
  summary?: string | null;
}

export interface ReportMeta {
  sources?: SourceRef[] | null;
  freshness_as_of?: string | null;
  range_start?: string | null;
}
