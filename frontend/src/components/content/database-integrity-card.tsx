/** Settings → Data tab: database integrity check + maintenance (repair) controls.
 *
 * The check is read-only and safe for any user; repair (checkpoint/reindex/
 * vacuum) is admin-gated on the backend (returns 403 otherwise). Foreign-key
 * violation counts are shown INFORMATIONALLY — FK enforcement is off by design
 * on SQLite — and never affect the healthy/issues badge.
 */
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getIntegrity, repairDatabase } from "@/lib/api/database";
import { ApiError } from "@/lib/api-client";
import type { IntegrityReport, RepairOperation, RepairResponse } from "@/lib/types/database";
import { toast } from "sonner";
import {
  Database as DatabaseIcon,
  Loader2,
  ChevronDown,
  TriangleAlert,
  ShieldCheck,
  Wrench,
  Info,
} from "lucide-react";

const REPAIR_OPS: {
  op: RepairOperation;
  label: string;
  desc: string;
  emphasize?: boolean;
}[] = [
  {
    op: "checkpoint",
    label: "Checkpoint WAL",
    desc: "Merge the write-ahead log back into the database and reclaim its disk space. Safe and fast.",
  },
  {
    op: "reindex",
    label: "Rebuild indexes",
    desc: "Rebuild all indexes — fixes index corruption and defrags. May briefly lock writes.",
  },
  {
    op: "vacuum",
    label: "Vacuum database",
    desc: "Rewrite and compact the database file, reclaiming all free space. Briefly blocks writes — back up first.",
    emphasize: true,
  },
];

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function DatabaseIntegrityCard() {
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [showTables, setShowTables] = useState(false);
  const [confirmOp, setConfirmOp] = useState<RepairOperation | null>(null);
  const [repairing, setRepairing] = useState(false);
  const [lastRepair, setLastRepair] = useState<RepairResponse | null>(null);

  async function runCheck() {
    setChecking(true);
    try {
      const r = await getIntegrity();
      setReport(r);
    } catch {
      toast.error("Integrity check failed");
    } finally {
      setChecking(false);
    }
  }

  async function doRepair(op: RepairOperation) {
    setRepairing(true);
    try {
      const result = await repairDatabase(op);
      setLastRepair(result);
      if (result.ok) {
        toast.success(result.message);
      } else {
        toast.error(result.message || "Repair could not complete");
      }
      // Refresh the report so before/after stats reflect the new state.
      void runCheck();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("A restore is in progress — try again after it finishes.");
      } else if (err instanceof ApiError && err.status === 403) {
        toast.error("Admin access required to repair the database.");
      } else {
        toast.error("Repair failed");
      }
    } finally {
      setRepairing(false);
      setConfirmOp(null);
    }
  }

  const totalRows = report ? report.tables.reduce((n, t) => n + t.count, 0) : 0;
  const unreadable = report?.tables.filter((t) => t.error).length ?? 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <DatabaseIcon className="h-4 w-4" /> Database Integrity
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1.5 text-xs"
            onClick={runCheck}
            disabled={checking}
          >
            {checking ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <ShieldCheck className="h-3 w-3" />
            )}
            {checking ? "Checking…" : report ? "Re-run check" : "Run check"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!report && !checking && (
          <p className="text-xs text-muted-foreground">
            Scan the database for structural corruption, view per-table row counts, and run
            maintenance like checkpointing the WAL, rebuilding indexes, or vacuuming to reclaim
            space.
          </p>
        )}

        {checking && !report && (
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            <Loader2 className="h-3 w-3 animate-spin" /> Scanning database…
          </p>
        )}

        {report && (
          <>
            {/* Status header */}
            <div className="flex flex-wrap items-center gap-2">
              {report.timed_out ? (
                <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-700">
                  <TriangleAlert className="h-3 w-3" /> Timed out
                </Badge>
              ) : report.ok ? (
                <Badge
                  variant="outline"
                  className="border-emerald-300 bg-emerald-50 text-emerald-700"
                >
                  <ShieldCheck className="h-3 w-3" /> Healthy
                </Badge>
              ) : (
                <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-700">
                  <TriangleAlert className="h-3 w-3" /> Issues found
                </Badge>
              )}
              <span className="text-[11px] text-muted-foreground capitalize">{report.engine}</span>
              <span className="text-[11px] text-muted-foreground/70">
                · {report.duration_ms} ms
              </span>
            </div>

            {/* Integrity messages */}
            {!report.timed_out && report.integrity_check[0] !== "ok" && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-2.5 text-xs">
                <p className="font-medium text-amber-800 mb-1">integrity_check</p>
                <pre className="whitespace-pre-wrap break-words text-amber-700 font-mono">
                  {report.integrity_check.join("\n")}
                </pre>
              </div>
            )}
            {report.notes.map((n, i) => (
              <p key={i} className="text-xs text-amber-700 flex items-start gap-1.5">
                <TriangleAlert className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>{n}</span>
              </p>
            ))}

            {/* Stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatTile label="Database size" value={formatBytes(report.stats.database_bytes)} />
              <StatTile label="Journal mode" value={report.stats.journal_mode ?? "—"} />
              <StatTile
                label="Free pages"
                value={
                  report.stats.freelist_pages != null && report.stats.page_count != null
                    ? `${report.stats.freelist_pages} / ${report.stats.page_count}`
                    : "—"
                }
              />
              {report.engine === "sqlite" ? (
                <StatTile label="WAL size" value={formatBytes(report.stats.wal_bytes)} />
              ) : (
                <StatTile label="Rows scanned" value={totalRows.toLocaleString()} />
              )}
            </div>

            {/* Tables */}
            <div className="rounded-lg border">
              <button
                onClick={() => setShowTables((s) => !s)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-muted/50 transition-colors"
              >
                <span className="font-medium">
                  {report.tables.length} tables · {totalRows.toLocaleString()} rows
                  {unreadable > 0 && (
                    <span className="text-amber-700"> · {unreadable} unreadable</span>
                  )}
                </span>
                <ChevronDown
                  className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${
                    showTables ? "rotate-180" : ""
                  }`}
                />
              </button>
              {showTables && (
                <div className="border-t max-h-56 overflow-y-auto">
                  {report.tables.map((t) => (
                    <div
                      key={t.name}
                      className="flex items-center justify-between px-3 py-1.5 text-xs border-b last:border-0"
                    >
                      <span className="font-mono text-muted-foreground">{t.name}</span>
                      {t.error ? (
                        <span
                          className="text-destructive truncate ml-2 max-w-[60%]"
                          title={t.error}
                        >
                          {t.error}
                        </span>
                      ) : (
                        <span className="tabular-nums">{t.count.toLocaleString()}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* FK informational line (SQLite) */}
            {report.engine === "sqlite" && (
              <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                <Info className="h-3 w-3 mt-0.5 shrink-0" />
                <span>
                  Referential-integrity check:{" "}
                  <span className="font-medium">{report.foreign_key_violations}</span> potential
                  foreign-key gap(s). Foreign-key checks are off by design on SQLite, so a non-zero
                  count reflects historical ID formats, not corruption.
                </span>
              </p>
            )}

            {/* Last repair outcome */}
            {lastRepair && (
              <div className="rounded-lg border bg-muted/30 p-2.5 text-xs">
                <p className="font-medium mb-1 flex items-center gap-1.5">
                  <Wrench className="h-3 w-3" />
                  Last repair: {lastRepair.operation}
                  {!lastRepair.ok && <span className="text-amber-700">— did not complete</span>}
                </p>
                <p className="text-muted-foreground">{lastRepair.message}</p>
                {lastRepair.before && lastRepair.after && (
                  <p className="text-muted-foreground/80 mt-1">
                    {formatBytes(lastRepair.before.database_bytes)} →{" "}
                    {formatBytes(lastRepair.after.database_bytes)}
                    {lastRepair.before.wal_bytes != null && lastRepair.after.wal_bytes != null && (
                      <>
                        {" "}
                        · WAL {formatBytes(lastRepair.before.wal_bytes)} →{" "}
                        {formatBytes(lastRepair.after.wal_bytes)}
                      </>
                    )}
                  </p>
                )}
              </div>
            )}
          </>
        )}

        {/* Repair section */}
        <div className="border-t pt-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <Wrench className="h-3.5 w-3.5" /> Maintenance &amp; repair
          </div>
          <div className="space-y-2">
            {REPAIR_OPS.map((r) => (
              <div
                key={r.op}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium">{r.label}</p>
                  <p className="text-[11px] text-muted-foreground">{r.desc}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className={`h-7 shrink-0 text-xs ${
                    r.emphasize ? "border-amber-300 text-amber-700 hover:bg-amber-50" : ""
                  }`}
                  onClick={() => setConfirmOp(r.op)}
                  disabled={repairing}
                >
                  Run
                </Button>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground/70">
            Admin only. Tip: <span className="font-medium">Back up now</span> before vacuuming — it
            rewrites the whole database file.
          </p>
        </div>
      </CardContent>

      {/* Repair confirmation */}
      <Dialog
        open={confirmOp !== null}
        onOpenChange={(o) => !repairing && !o && setConfirmOp(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Run {confirmOp ? labelFor(confirmOp) : ""}?</DialogTitle>
            <DialogDescription>{confirmOp ? descFor(confirmOp) : ""}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOp(null)} disabled={repairing}>
              Cancel
            </Button>
            <Button
              onClick={() => confirmOp && doRepair(confirmOp)}
              disabled={repairing}
              className={
                confirmOp === "vacuum"
                  ? "border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200"
                  : ""
              }
            >
              {repairing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Working…
                </>
              ) : (
                "Run"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-2.5 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="text-sm font-medium tabular-nums truncate">{value}</p>
    </div>
  );
}

function labelFor(op: RepairOperation): string {
  return REPAIR_OPS.find((r) => r.op === op)?.label ?? op;
}

function descFor(op: RepairOperation): string {
  return (
    REPAIR_OPS.find((r) => r.op === op)?.desc ?? "This performs maintenance on the live database."
  );
}
