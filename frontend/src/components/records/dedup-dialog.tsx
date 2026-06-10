import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { findDuplicates, mergeRecords, deleteRecord } from "@/lib/api/records";
import type { DedupResponse } from "@/lib/types/health-record";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import {
  Loader2,
  Copy,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Paperclip,
  Crown,
  Trash2,
} from "lucide-react";
import { toDisplayDate } from "@/lib/utils";
import { mutate } from "swr";

const REASON_LABELS: Record<string, { label: string; color: string }> = {
  same_type_adjacent_date: { label: "Same type + date", color: "bg-blue-100 text-blue-700" },
  same_provider_diagnosis: {
    label: "Same provider + diagnosis",
    color: "bg-purple-100 text-purple-700",
  },
  similar_content: { label: "Similar content", color: "bg-amber-100 text-amber-700" },
  same_attachment: { label: "Same file", color: "bg-green-100 text-green-700" },
};

interface DedupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  memberId: string;
}

export function DedupDialog({ open, onOpenChange, memberId }: DedupDialogProps) {
  const [scanning, setScanning] = useState(false);
  const [merging, setMerging] = useState(false);
  const [result, setResult] = useState<DedupResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedKeepers, setSelectedKeepers] = useState<Record<string, string>>({});
  const [mergedGroups, setMergedGroups] = useState<Set<number>>(new Set());
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleScan() {
    setScanning(true);
    setError(null);
    setResult(null);
    setSelectedKeepers({});
    setMergedGroups(new Set());
    try {
      const data = await findDuplicates(memberId);
      setResult(data);
      // Initialize keepers with recommendations
      const initial: Record<string, string> = {};
      data.groups.forEach((g, i) => {
        initial[`group-${i}`] = g.recommended_keeper_id;
      });
      setSelectedKeepers(initial);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to scan for duplicates");
    } finally {
      setScanning(false);
    }
  }

  async function handleMerge(groupIndex: number) {
    const group = result!.groups[groupIndex];
    const keeperId = selectedKeepers[`group-${groupIndex}`] || group.recommended_keeper_id;
    const loserIds = group.records.filter((r) => r.id !== keeperId).map((r) => r.id);

    if (loserIds.length === 0) return;

    setMerging(true);
    try {
      await mergeRecords(memberId, keeperId, loserIds);
      setMergedGroups((prev) => new Set([...prev, groupIndex]));
      // Refresh member detail data
      mutate(`member-dashboard-${memberId}`);
      mutate(`member-${memberId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to merge records");
    } finally {
      setMerging(false);
    }
  }

  async function handleDelete(recordId: string) {
    setDeletingId(recordId);
    try {
      await deleteRecord(memberId, recordId);
      setDeletedIds((prev) => new Set([...prev, recordId]));
      mutate(`member-dashboard-${memberId}`);
      mutate(`member-${memberId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete record");
    } finally {
      setDeletingId(null);
    }
  }

  function handleClose() {
    setResult(null);
    setError(null);
    setSelectedKeepers({});
    setMergedGroups(new Set());
    setDeletedIds(new Set());
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="h-5 w-5" />
            Find Duplicate Records
          </DialogTitle>
          <DialogDescription>
            Scan this member's records for potential duplicates and merge them.
          </DialogDescription>
        </DialogHeader>

        {!result && !scanning && (
          <div className="py-6 text-center space-y-4">
            <p className="text-sm text-muted-foreground">
              This will scan all records and find potential duplicates based on:
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {Object.values(REASON_LABELS).map((r) => (
                <Badge key={r.label} variant="secondary" className="text-xs">
                  {r.label}
                </Badge>
              ))}
            </div>
            <Button onClick={handleScan} size="sm">
              Scan for Duplicates
            </Button>
          </div>
        )}

        {scanning && (
          <div className="py-8 flex flex-col items-center gap-2">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Scanning records...</p>
          </div>
        )}

        {error && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {result && !scanning && (
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Scanned {result.total_records_scanned} records — found{" "}
              {result.groups.length === 0 ? "no" : result.groups.length} potential duplicate
              {result.groups.length !== 1 ? " groups" : " group"}
            </p>

            {result.groups.length === 0 && (
              <div className="py-4 text-center">
                <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto mb-2" />
                <p className="text-sm font-medium text-green-700">No duplicates found!</p>
                <p className="text-xs text-muted-foreground mt-1">
                  All records appear to be unique.
                </p>
              </div>
            )}

            {result.groups.map((group, gi) => {
              const isMerged = mergedGroups.has(gi);
              const selectedKeeper = selectedKeepers[`group-${gi}`] || group.recommended_keeper_id;

              return (
                <div
                  key={gi}
                  className={`rounded-lg border p-3 space-y-3 ${
                    isMerged ? "border-green-200 bg-green-50/50" : "border-amber-200 bg-amber-50/30"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold">
                        Group {gi + 1} — {group.records.length} records
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        Score: {group.score}
                      </Badge>
                    </div>
                    {isMerged ? (
                      <Badge className="bg-green-100 text-green-700 text-[10px]">
                        <CheckCircle2 className="h-3 w-3 mr-1" />
                        Merged
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleMerge(gi)}
                        disabled={merging}
                        className="h-7 text-xs"
                      >
                        {merging ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                        Merge into keeper
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1">
                    {group.match_reasons.map((reason) => {
                      const info = REASON_LABELS[reason];
                      return info ? (
                        <Badge key={reason} className={`text-[10px] ${info.color}`}>
                          {info.label}
                        </Badge>
                      ) : null;
                    })}
                  </div>

                  {!isMerged && (
                    <div className="space-y-2">
                      <p className="text-[11px] text-muted-foreground">
                        Click a record to select as keeper:
                      </p>
                      {group.records.map((rec) => {
                        const isRecommended = rec.id === group.recommended_keeper_id;
                        const isSelected = rec.id === selectedKeeper;
                        const isDeleted = deletedIds.has(rec.id);
                        const isDeleting = deletingId === rec.id;
                        if (isDeleted)
                          return (
                            <div
                              key={rec.id}
                              className="flex items-center gap-2 rounded-md border border-muted bg-muted/30 p-2 text-xs text-muted-foreground"
                            >
                              <CheckCircle2 className="h-3 w-3 text-green-500" />
                              <span>Record deleted</span>
                            </div>
                          );
                        return (
                          <div
                            key={rec.id}
                            className={`flex items-start gap-2 rounded-md border p-2 text-xs transition-colors ${
                              isSelected
                                ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                                : "border-muted bg-background hover:bg-muted/50"
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedKeepers((prev) => ({ ...prev, [`group-${gi}`]: rec.id }))
                              }
                              className="flex items-start gap-2 flex-1 text-left cursor-pointer"
                            >
                              <div className="mt-0.5 h-4 w-4 rounded-full border-2 flex items-center justify-center shrink-0">
                                {isSelected && <div className="h-2 w-2 rounded-full bg-primary" />}
                              </div>
                              <div className="flex-1 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium">
                                    {(RECORD_TYPE_LABELS as Record<string, string>)[
                                      rec.record_type
                                    ] || rec.record_type}
                                  </span>
                                  <span className="text-muted-foreground">
                                    {toDisplayDate(rec.record_date)}
                                  </span>
                                  {isRecommended && <Crown className="h-3 w-3 text-amber-500" />}
                                </div>
                                {rec.diagnosis && (
                                  <p className="text-muted-foreground">{rec.diagnosis}</p>
                                )}
                                {rec.provider_name && (
                                  <p className="text-muted-foreground">
                                    Provider: {rec.provider_name}
                                  </p>
                                )}
                                <div className="flex items-center gap-3 text-muted-foreground">
                                  {rec.prescription_text && (
                                    <span className="flex items-center gap-0.5">
                                      <FileText className="h-3 w-3" />
                                      Rx
                                    </span>
                                  )}
                                  {rec.attachment_count > 0 && (
                                    <span className="flex items-center gap-0.5">
                                      <Paperclip className="h-3 w-3" />
                                      {rec.attachment_count} file
                                      {rec.attachment_count !== 1 ? "s" : ""}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
                              disabled={isDeleting}
                              onClick={() => handleDelete(rec.id)}
                              title="Delete this record"
                            >
                              {isDeleting ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Trash2 className="h-3 w-3" />
                              )}
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {isMerged && (
                    <p className="text-xs text-green-700">
                      Records merged successfully. Losers have been archived.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
