import { useState, useMemo, useRef, useCallback, memo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowUpDown, ArrowUp, ArrowDown, FileText } from "lucide-react";
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
import { TranscriptionReportView } from "@/components/records/transcription-report-view";
import { extractReason, extractSummary } from "@/lib/record-utils";
import { formatDate } from "@/lib/utils";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface RecordsTableProps {
  records: HealthRecordResponse[];
  memberNames?: Record<string, string>;
  membersById?: Record<string, FamilyMemberResponse>;
  onRowClick?: (record: HealthRecordResponse) => void;
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
}

type SortKey = "record_date" | "record_type" | "provider_name" | "reason";
type SortDir = "asc" | "desc";

const VIRTUALIZE_THRESHOLD = 80;
const ESTIMATED_ROW_HEIGHT = 44;

/* ── Shared hover popout: the "Medical Records Transcription Report" ── */

function RecordReportPopover({
  record,
  member,
}: {
  record: HealthRecordResponse;
  member?: FamilyMemberResponse | null;
}) {
  // The popout is only meaningful for visit/lab reports (the template renders
  // from their structured fields; other types have no report format).
  if (record.record_type !== "doctor_visit" && record.record_type !== "lab_report") {
    return <span className="inline-flex items-center justify-center w-[22px] h-[22px]" />;
  }
  return (
    <Popover modal={false}>
      <PopoverTrigger
        openOnHover
        delay={300}
        closeDelay={200}
        className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:text-blue-500 hover:bg-blue-50 transition-colors cursor-pointer"
        aria-label="Preview transcription report"
      >
        <FileText className="h-3.5 w-3.5" />
      </PopoverTrigger>
      <PopoverContent
        side="left"
        sideOffset={8}
        align="start"
        className="w-[28rem] max-h-[420px] overflow-y-auto p-0"
      >
        <div className="p-3 space-y-2">
          <PopoverHeader>
            <PopoverTitle className="text-xs flex items-center gap-2">
              <RecordTypeBadge type={record.record_type} />
              {formatDate(record.record_date)}
              {record.provider_name && (
                <span className="text-muted-foreground font-normal">· {record.provider_name}</span>
              )}
            </PopoverTitle>
          </PopoverHeader>
          <TranscriptionReportView record={record} member={member} compact />
          <PopoverDescription className="text-[10px] pt-1 border-t">
            Click row to view full record
          </PopoverDescription>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/* ── Memoized row component ── */

interface RecordRowProps {
  record: HealthRecordResponse;
  hasSelection: boolean;
  isSelected: boolean;
  memberName?: string;
  member?: FamilyMemberResponse | null;
  onRowClick?: (record: HealthRecordResponse) => void;
  onToggleRow: (id: string) => void;
}

const RecordRow = memo(function RecordRow({
  record,
  hasSelection,
  isSelected,
  memberName,
  member,
  onRowClick,
  onToggleRow,
}: RecordRowProps) {
  const reason = extractReason(record);
  const summaryLine = extractSummary(record);

  return (
    <TableRow className="cursor-pointer" onClick={() => onRowClick?.(record)}>
      {hasSelection && (
        <TableCell className="py-2 px-2 w-[40px]" onClick={(e) => e.stopPropagation()}>
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => onToggleRow(record.id)}
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
        <span className="text-sm text-muted-foreground">{record.provider_name || "—"}</span>
      </TableCell>
      <TableCell className="py-2 max-w-[300px]">
        {reason ? (
          <p className="text-sm font-medium truncate">{reason}</p>
        ) : (
          <p className="text-sm text-muted-foreground">—</p>
        )}
        {summaryLine && (
          <p className="text-xs text-muted-foreground/70 truncate mt-0.5">{summaryLine}</p>
        )}
      </TableCell>
      {/* File icon — hover to preview the transcription report */}
      <TableCell className="py-2 w-[36px] text-center" onClick={(e) => e.stopPropagation()}>
        <RecordReportPopover record={record} member={member} />
      </TableCell>
      {memberName !== undefined && (
        <TableCell className="py-2 w-[120px]">
          <span className="text-sm text-muted-foreground">{memberName}</span>
        </TableCell>
      )}
    </TableRow>
  );
});

export const RecordsTable = memo(function RecordsTable({
  records,
  memberNames,
  membersById,
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

  const toggleAll = useCallback(() => {
    if (!onSelectionChange) return;
    if (allSelected) onSelectionChange(new Set());
    else onSelectionChange(new Set(records.map((r) => r.id)));
  }, [onSelectionChange, allSelected, records]);

  const toggleRow = useCallback(
    (id: string) => {
      if (!onSelectionChange || !selectedIds) return;
      const next = new Set(selectedIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      onSelectionChange(next);
    },
    [onSelectionChange, selectedIds]
  );

  const handleRowClick = useCallback(
    (record: HealthRecordResponse) => onRowClick?.(record),
    [onRowClick]
  );

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

  const needsVirtualization = sorted.length > VIRTUALIZE_THRESHOLD;

  // TanStack Virtual virtualizer for large lists
  const virtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 10,
    enabled: needsVirtualization,
  });

  const memberFor = useCallback(
    (record: HealthRecordResponse) => membersById?.[record.family_member_id],
    [membersById]
  );

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
              <span className="sr-only">Report</span>
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
      <div
        ref={scrollRef}
        style={needsVirtualization ? { maxHeight: "600px", overflowY: "auto" } : undefined}
      >
        {needsVirtualization ? (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: "100%",
              position: "relative",
            }}
          >
            <Table>
              <TableBody>
                {virtualizer.getVirtualItems().map((virtualRow) => {
                  const record = sorted[virtualRow.index];
                  return (
                    <TableRow
                      key={record.id}
                      data-index={virtualRow.index}
                      ref={(el) => virtualizer.measureElement(el)}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                      className="cursor-pointer"
                      onClick={() => handleRowClick(record)}
                    >
                      {hasSelection && (
                        <TableCell
                          className="py-2 px-2 w-[40px]"
                          onClick={(e) => e.stopPropagation()}
                        >
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
                        <span className="text-sm tabular-nums">
                          {formatDate(record.record_date)}
                        </span>
                      </TableCell>
                      <TableCell className="py-2 w-[130px]">
                        <span className="text-sm text-muted-foreground">
                          {record.provider_name || "—"}
                        </span>
                      </TableCell>
                      <TableCell className="py-2 max-w-[300px]">
                        {(() => {
                          const reason = extractReason(record);
                          const summaryLine = extractSummary(record);
                          return (
                            <>
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
                            </>
                          );
                        })()}
                      </TableCell>
                      <TableCell
                        className="py-2 w-[36px] text-center"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <RecordReportPopover record={record} member={memberFor(record)} />
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
        ) : (
          <Table>
            <TableBody>
              {sorted.map((record) => (
                <RecordRow
                  key={record.id}
                  record={record}
                  hasSelection={hasSelection}
                  isSelected={selectedIds?.has(record.id) ?? false}
                  memberName={memberNames?.[record.family_member_id]}
                  member={memberFor(record)}
                  onRowClick={handleRowClick}
                  onToggleRow={toggleRow}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      {needsVirtualization && (
        <div className="px-3 py-1.5 border-t text-xs text-muted-foreground text-center">
          Showing {sorted.length} records — scroll to see more
        </div>
      )}
    </div>
  );
});
