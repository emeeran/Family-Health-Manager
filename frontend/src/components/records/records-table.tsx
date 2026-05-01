import { useState, useMemo } from "react";
import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { extractReason, extractSummary } from "@/lib/record-utils";
import { formatDate } from "@/lib/utils";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface RecordsTableProps {
  records: HealthRecordResponse[];
  memberNames?: Record<string, string>;
  onRowClick?: (record: HealthRecordResponse) => void;
}

type SortKey = "record_date" | "record_type" | "provider_name" | "reason";
type SortDir = "asc" | "desc";

export function RecordsTable({ records, memberNames, onRowClick }: RecordsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("record_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "record_date" ? "desc" : "asc");
    }
  }

  const sorted = useMemo(() => {
    return [...records].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "record_date":
          cmp = a.record_date.localeCompare(b.record_date);
          break;
        case "record_type":
          cmp = a.record_type.localeCompare(b.record_type);
          break;
        case "provider_name":
          cmp = (a.provider_name || "").localeCompare(b.provider_name || "");
          break;
        case "reason":
          cmp = extractReason(a).localeCompare(extractReason(b));
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [records, sortKey, sortDir]);

  function SortIcon({ column }: { column: SortKey }) {
    if (sortKey !== column) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />;
    return sortDir === "asc" ? (
      <ArrowUp className="h-3 w-3 ml-1 text-primary" />
    ) : (
      <ArrowDown className="h-3 w-3 ml-1 text-primary" />
    );
  }

  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[110px]">
              <button
                onClick={() => toggleSort("record_type")}
                className="inline-flex items-center text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                Type <SortIcon column="record_type" />
              </button>
            </TableHead>
            <TableHead className="w-[100px]">
              <button
                onClick={() => toggleSort("record_date")}
                className="inline-flex items-center text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                Date <SortIcon column="record_date" />
              </button>
            </TableHead>
            <TableHead className="w-[130px]">
              <button
                onClick={() => toggleSort("provider_name")}
                className="inline-flex items-center text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                Provider <SortIcon column="provider_name" />
              </button>
            </TableHead>
            <TableHead>
              <button
                onClick={() => toggleSort("reason")}
                className="inline-flex items-center text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                Diagnosis / Reason <SortIcon column="reason" />
              </button>
            </TableHead>
            {memberNames && (
              <TableHead className="w-[120px]">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Member
                </span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((record) => {
            const reason = extractReason(record);
            const summary = extractSummary(record);
            return (
              <TableRow
                key={record.id}
                className="cursor-pointer"
                onClick={() => onRowClick?.(record)}
              >
                <TableCell className="py-2">
                  <RecordTypeBadge type={record.record_type} />
                </TableCell>
                <TableCell className="py-2">
                  <span className="text-sm tabular-nums">{formatDate(record.record_date)}</span>
                </TableCell>
                <TableCell className="py-2">
                  <span className="text-sm text-muted-foreground">
                    {record.provider_name || "—"}
                  </span>
                </TableCell>
                <TableCell className="py-2 max-w-[300px]">
                  {reason ? (
                    <p className="text-sm font-medium truncate">{reason}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground">—</p>
                  )}
                  {summary && (
                    <p className="text-xs text-muted-foreground/70 truncate mt-0.5">{summary}</p>
                  )}
                </TableCell>
                {memberNames && (
                  <TableCell className="py-2">
                    <span className="text-sm text-muted-foreground">
                      {memberNames[record.family_member_id] || "—"}
                    </span>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
