import { useState, useMemo, useRef } from "react";
import { ArrowUpDown, ArrowUp, ArrowDown, Eye } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverDescription,
  PopoverTrigger,
} from "@/components/ui/popover";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { extractReason, extractSummary } from "@/lib/record-utils";
import { formatDate } from "@/lib/utils";
import { simpleMarkdown } from "@/lib/markdown";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface RecordsTableProps {
  records: HealthRecordResponse[];
  memberNames?: Record<string, string>;
  onRowClick?: (record: HealthRecordResponse) => void;
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
}

type SortKey = "record_date" | "record_type" | "provider_name" | "reason";
type SortDir = "asc" | "desc";

const VIRTUALIZE_THRESHOLD = 80;
const MAX_VISIBLE_ROWS = 60;
const ROW_HEIGHT_PX = 44;

export function RecordsTable({
  records,
  memberNames,
  onRowClick,
  selectedIds,
  onSelectionChange,
}: RecordsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("record_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const scrollRef = useRef<HTMLDivElement>(null);

  const hasSelection = !!selectedIds && !!onSelectionChange;
  const allSelected =
    hasSelection && records.length > 0 && records.every((r) => selectedIds.has(r.id));
  const someSelected = hasSelection && records.some((r) => selectedIds.has(r.id)) && !allSelected;

  function toggleAll() {
    if (!onSelectionChange) return;
    if (allSelected) onSelectionChange(new Set());
    else onSelectionChange(new Set(records.map((r) => r.id)));
  }

  function toggleRow(id: string) {
    if (!onSelectionChange || !selectedIds) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  }

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

  // For very large record sets, use CSS containment with max-height scroll
  const needsScroll = sorted.length > VIRTUALIZE_THRESHOLD;
  const scrollStyle = needsScroll
    ? { maxHeight: `${MAX_VISIBLE_ROWS * ROW_HEIGHT_PX}px`, overflowY: "auto" as const }
    : undefined;

  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {hasSelection && (
              <TableHead className="w-[40px] px-2">
                <Checkbox
                  checked={allSelected}
                  ref={(el) => {
                    if (el && someSelected) el.setAttribute("data-state", "indeterminate");
                  }}
                  onCheckedChange={toggleAll}
                  aria-label="Select all rows"
                />
              </TableHead>
            )}
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
            <TableHead className="w-[36px] px-1">
              <span className="sr-only">Summary</span>
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
      </Table>
      <div ref={scrollRef} style={scrollStyle} className={needsScroll ? "contain-content" : ""}>
        <Table>
          <TableBody>
            {sorted.map((record) => {
              const reason = extractReason(record);
              const summaryLine = extractSummary(record);
              const hasConsultationSummary = !!record.summary;
              return (
                <TableRow
                  key={record.id}
                  className="cursor-pointer"
                  onClick={() => onRowClick?.(record)}
                >
                  {hasSelection && (
                    <TableCell className="py-2 px-2 w-[40px]" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds?.has(record.id) ?? false}
                        onCheckedChange={() => toggleRow(record.id)}
                        aria-label={`Select record ${record.id}`}
                      />
                    </TableCell>
                  )}
                  <TableCell className="py-2 w-[110px]">
                    <RecordTypeBadge type={record.record_type} />
                  </TableCell>
                  <TableCell className="py-2 w-[100px]">
                    <span className="text-sm tabular-nums">{formatDate(record.record_date)}</span>
                  </TableCell>
                  <TableCell className="py-2 w-[130px]">
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
                    {summaryLine && (
                      <p className="text-xs text-muted-foreground/70 truncate mt-0.5">
                        {summaryLine}
                      </p>
                    )}
                  </TableCell>
                  {/* Eye icon — hover to preview consultation summary */}
                  <TableCell
                    className="py-2 w-[36px] text-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {hasConsultationSummary ? (
                      <Popover modal={false}>
                        <PopoverTrigger
                          openOnHover
                          delay={300}
                          closeDelay={200}
                          className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:text-blue-500 hover:bg-blue-50 transition-colors cursor-pointer"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </PopoverTrigger>
                        <PopoverContent
                          side="left"
                          sideOffset={8}
                          align="start"
                          className="w-96 max-h-[360px] overflow-y-auto p-0"
                        >
                          <div className="p-3 space-y-2">
                            <PopoverHeader>
                              <PopoverTitle className="text-xs flex items-center gap-2">
                                <RecordTypeBadge type={record.record_type} />
                                {formatDate(record.record_date)}
                                {record.provider_name && (
                                  <span className="text-muted-foreground font-normal">
                                    · {record.provider_name}
                                  </span>
                                )}
                              </PopoverTitle>
                            </PopoverHeader>
                            <div
                              className="text-xs text-muted-foreground leading-relaxed prose prose-sm max-w-none prose-table:text-[11px] prose-th:px-1.5 prose-th:py-0.5 prose-td:px-1.5 prose-td:py-0.5 prose-th:bg-muted/50"
                              dangerouslySetInnerHTML={{
                                __html: simpleMarkdown(record.summary || ""),
                              }}
                            />
                            <PopoverDescription className="text-[10px] pt-1 border-t">
                              Click row to view full record
                            </PopoverDescription>
                          </div>
                        </PopoverContent>
                      </Popover>
                    ) : (
                      <span className="inline-flex items-center justify-center w-[22px] h-[22px]" />
                    )}
                  </TableCell>
                  {memberNames && (
                    <TableCell className="py-2 w-[120px]">
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
      {needsScroll && (
        <div className="px-3 py-1.5 border-t text-xs text-muted-foreground text-center">
          Showing {sorted.length} records — scroll to see more
        </div>
      )}
    </div>
  );
}
