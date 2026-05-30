import { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  downloadBackupExport,
  validateBackup,
  importBackup,
  cleanupStagedBackup,
} from "@/lib/api/backup";
import type {
  BackupValidationResponse,
  BackupImportResponse,
  ImportMode,
} from "@/lib/types/backup";

type Step = "idle" | "validating" | "reviewing" | "importing" | "complete" | "error";

export function BackupRestoreSection() {
  const [step, setStep] = useState<Step>("idle");
  const [validation, setValidation] = useState<BackupValidationResponse | null>(null);
  const [importResult, setImportResult] = useState<BackupImportResponse | null>(null);
  const [mode, setMode] = useState<ImportMode>("merge");
  const [errorMsg, setErrorMsg] = useState("");
  const [downloading, setDownloading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Export ──────────────────────────────────────────────────

  async function handleExport() {
    setDownloading(true);
    try {
      const blob = await downloadBackupExport();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "backup.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } finally {
      setDownloading(false);
    }
  }

  // ── Import: validate ────────────────────────────────────────

  async function handleFileSelected() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setStep("validating");
    setErrorMsg("");
    try {
      const result = await validateBackup(file);
      setValidation(result);
      if (!result.valid) {
        setStep("error");
        setErrorMsg(result.errors.join("; ") || "Invalid backup archive");
        return;
      }
      setStep("reviewing");
    } catch (e) {
      setStep("error");
      setErrorMsg(e instanceof Error ? e.message : "Validation failed");
    }
  }

  // ── Import: execute ─────────────────────────────────────────

  async function handleImport() {
    if (!validation) return;
    setStep("importing");
    try {
      const result = await importBackup({ validation_id: validation.validation_id, mode });
      setImportResult(result);
      setStep("complete");
    } catch (e) {
      setStep("error");
      setErrorMsg(e instanceof Error ? e.message : "Import failed");
    }
  }

  // ── Cancel / reset ──────────────────────────────────────────

  async function handleCancel() {
    if (validation?.validation_id) {
      await cleanupStagedBackup(validation.validation_id).catch(() => {});
    }
    resetState();
  }

  function resetState() {
    setStep("idle");
    setValidation(null);
    setImportResult(null);
    setErrorMsg("");
    setMode("merge");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // ── Render ──────────────────────────────────────────────────

  return (
    <>
      <Separator className="my-2" />

      <Card>
        <CardHeader>
          <CardTitle>Data Management</CardTitle>
          <CardDescription>Export or import your household health data</CardDescription>
        </CardHeader>
        <CardContent>
          {step === "idle" && (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row">
                <Button onClick={handleExport} disabled={downloading} variant="outline">
                  {downloading ? "Preparing download..." : "Export Backup"}
                </Button>
                <Button onClick={() => fileInputRef.current?.click()} variant="outline">
                  Import Backup
                </Button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={handleFileSelected}
              />
              <p className="text-xs text-muted-foreground">
                Backups include all family members, health records, providers, attachments,
                conversations, reminders, and notifications.
              </p>
            </div>
          )}

          {step === "validating" && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Validating backup archive...</p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
              </div>
            </div>
          )}

          {step === "reviewing" && validation?.manifest && (
            <div className="space-y-4">
              <div className="rounded-lg border p-3 space-y-2 text-sm">
                <p>
                  <span className="text-muted-foreground">Household:</span>{" "}
                  <strong>{validation.manifest.household_name}</strong>
                </p>
                <p>
                  <span className="text-muted-foreground">Created:</span>{" "}
                  {new Date(validation.manifest.created_at).toLocaleString()}
                </p>
                <p>
                  <span className="text-muted-foreground">Backup version:</span>{" "}
                  {validation.manifest.version}
                </p>
                <Separator />
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <span>{validation.manifest.counts.members} member(s)</span>
                  <span>{validation.manifest.counts.health_records} record(s)</span>
                  <span>{validation.manifest.counts.providers} provider(s)</span>
                  <span>{validation.manifest.counts.attachments} attachment(s)</span>
                  <span>{validation.manifest.counts.conversations} conversation(s)</span>
                  <span>{validation.manifest.counts.messages} message(s)</span>
                  <span>{validation.manifest.counts.reminders} reminder(s)</span>
                  <span>{validation.manifest.counts.notifications} notification(s)</span>
                </div>
              </div>

              {validation.warnings.length > 0 && (
                <div className="rounded-lg border border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-900/20 p-3">
                  <p className="text-xs font-medium text-yellow-700 dark:text-yellow-400">
                    Warnings:
                  </p>
                  {validation.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-yellow-600 dark:text-yellow-500">
                      {w}
                    </p>
                  ))}
                </div>
              )}

              <div className="space-y-2">
                <Label>Import mode</Label>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={mode === "merge" ? "default" : "outline"}
                    onClick={() => setMode("merge")}
                  >
                    Merge (keep existing)
                  </Button>
                  <Button
                    size="sm"
                    variant={mode === "replace" ? "destructive" : "outline"}
                    onClick={() => setMode("replace")}
                  >
                    Replace all
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {mode === "merge"
                    ? "Keeps your existing data and adds backup records. Duplicates are skipped."
                    : "Deletes all current household data before importing. This cannot be undone."}
                </p>
              </div>

              <div className="flex gap-2">
                <Button onClick={handleImport}>Confirm Import</Button>
                <Button variant="ghost" onClick={handleCancel}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {step === "importing" && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Importing data...</p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
              </div>
            </div>
          )}

          {step === "complete" && importResult && (
            <div className="space-y-4">
              <div className="rounded-lg border border-green-500/50 bg-green-50/50 dark:bg-green-900/20 p-3 space-y-2">
                <p className="text-sm font-medium text-green-700 dark:text-green-400">
                  Import complete
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <span>{importResult.imported.members} member(s) imported</span>
                  <span>{importResult.imported.health_records} record(s) imported</span>
                  <span>{importResult.imported.attachments} attachment(s) imported</span>
                  <span>{importResult.imported.conversations} conversation(s) imported</span>
                  {importResult.failed > 0 && (
                    <span className="col-span-2 text-red-600">{importResult.failed} error(s)</span>
                  )}
                </div>
                {importResult.errors.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-red-600">Errors:</p>
                    {importResult.errors.slice(0, 5).map((e, i) => (
                      <p key={i} className="text-xs text-red-500">
                        {e}
                      </p>
                    ))}
                  </div>
                )}
              </div>
              <Button onClick={resetState}>Done</Button>
            </div>
          )}

          {step === "error" && (
            <div className="space-y-3">
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
                <p className="text-sm font-medium text-destructive">Error</p>
                <p className="text-xs text-destructive/80">{errorMsg}</p>
              </div>
              <Button variant="outline" onClick={resetState}>
                Try Again
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
