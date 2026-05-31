import { useMemo } from "react";
import type { HealthRecordResponse } from "@/lib/types/health-record";

/** Extract HbA1c chart data from health records. */
export function extractHba1cData(
  records: HealthRecordResponse[],
  memberNames: Record<string, string>
) {
  const entries: { date: string; value: number; memberName: string }[] = [];
  const activeRecords = records.filter((r) => !r.is_deleted);

  for (const r of activeRecords) {
    if (r.record_type !== "blood_glucose" && r.record_type !== "doctor_visit") continue;
    try {
      const parsed = JSON.parse(r.clinical_data || "{}");
      if (parsed.hba1c_value) {
        const v = parseFloat(parsed.hba1c_value);
        if (!isNaN(v))
          entries.push({
            date: r.record_date,
            value: v,
            memberName: memberNames[r.family_member_id] || "Unknown",
          });
        continue;
      }
      for (const key of ["lab_results", "tests"]) {
        const labs = parsed[key];
        if (!Array.isArray(labs)) continue;
        for (const test of labs) {
          const name = (test.test_name || "").toLowerCase();
          if (name.includes("hba1c") || name.includes("a1c") || name.includes("glycated")) {
            const match = (test.result || "").match(/(\d+\.?\d*)/);
            if (match) {
              entries.push({
                date: r.record_date,
                value: parseFloat(match[1]),
                memberName: memberNames[r.family_member_id] || "Unknown",
              });
              break;
            }
          }
        }
      }
    } catch {
      /* skip */
    }
  }
  return entries.sort((a, b) => a.date.localeCompare(b.date));
}

/** Transform raw HbA1c entries into chart rows (pivoted by date). */
export function hba1cEntriesToChartRows(
  entries: { date: string; value: number; memberName: string }[],
  maxRows = 15
) {
  const byDate: Record<string, { date: string; [k: string]: string | number }> = {};
  for (const e of entries) {
    if (!byDate[e.date]) byDate[e.date] = { date: e.date };
    byDate[e.date][e.memberName] = e.value;
  }
  return Object.values(byDate).slice(-maxRows);
}

/** Hook: compute HbA1c chart data from records. */
export function useHba1cChartData(
  records: HealthRecordResponse[],
  memberNames: Record<string, string>
) {
  const entries = useMemo(() => extractHba1cData(records, memberNames), [records, memberNames]);
  const chartRows = useMemo(() => hba1cEntriesToChartRows(entries), [entries]);
  const members = useMemo(() => [...new Set(entries.map((e) => e.memberName))], [entries]);
  return { entries, chartRows, members };
}
