/** Settings → Data tab: storage overview, scheduled + manual backups, archives,
 * export/import, and the database-reset danger zone. */
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BackupRestoreSection } from "@/components/content/backup-restore";
import { ResetDatabaseDialog } from "@/components/shared/reset-database-dialog";
import {
  getBackupStatus,
  listBackupArchives,
  runBackup,
  deleteBackupArchive,
  backupArchiveDownloadUrl,
} from "@/lib/api/backup";
import type { BackupArchive, BackupStatus } from "@/lib/types/backup";
import type { FeatureSettings } from "@/lib/types/household";
import { toast } from "sonner";
import { RefreshCw, Loader2, Download, Trash2, HardDrive } from "lucide-react";

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return "—";
  }
}

const SCHEDULE_LABELS: Record<FeatureSettings["backup_schedule"], string> = {
  off: "Disabled",
  daily: "Daily",
  weekly: "Weekly",
};

export function DataTab({
  featureSettings,
  onUpdateSetting,
}: {
  featureSettings: FeatureSettings | null;
  onUpdateSetting: <K extends keyof FeatureSettings>(key: K, value: FeatureSettings[K]) => void;
}) {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [archives, setArchives] = useState<BackupArchive[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  // Local input state for keep-max (persist on blur to avoid per-keystroke saves).
  const [keepMaxDraft, setKeepMaxDraft] = useState("");

  async function refresh() {
    try {
      const [s, a] = await Promise.all([getBackupStatus(), listBackupArchives()]);
      setStatus(s);
      setArchives(a);
    } catch {
      toast.error("Failed to load backup status");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  // Sync the keep-max draft when settings load/change.
  useEffect(() => {
    if (featureSettings) setKeepMaxDraft(String(featureSettings.backup_keep_max));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-sync when keep_max changes; depending on featureSettings would wipe in-progress edits
  }, [featureSettings?.backup_keep_max]);

  async function handleRunBackup() {
    setRunning(true);
    try {
      const result = await runBackup();
      toast.success(`Backup created — ${formatBytes(result.size_bytes)}`);
      await refresh();
    } catch {
      toast.error("Backup failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleDelete(name: string) {
    setDeleting(name);
    try {
      await deleteBackupArchive(name);
      toast.success("Archive deleted");
      setArchives((prev) => prev.filter((a) => a.name !== name));
      await refresh();
    } catch {
      toast.error("Failed to delete archive");
    } finally {
      setDeleting(null);
    }
  }

  function commitKeepMax() {
    const n = parseInt(keepMaxDraft, 10);
    if (Number.isFinite(n) && n >= 1 && n <= 100 && n !== featureSettings?.backup_keep_max) {
      onUpdateSetting("backup_keep_max", n);
    } else if (featureSettings) {
      setKeepMaxDraft(String(featureSettings.backup_keep_max));
    }
  }

  const diskUsedPct = status ? Math.round((status.disk.used / status.disk.total) * 100) : 0;

  return (
    <div className="space-y-6 pt-2">
      {/* Storage overview */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <HardDrive className="h-4 w-4" /> Storage
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading || !status ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="text-lg font-semibold">{formatBytes(status.attachments_bytes)}</p>
                  <p className="text-[11px] text-muted-foreground">Medical records</p>
                </div>
                <div>
                  <p className="text-lg font-semibold">{formatBytes(status.database_bytes)}</p>
                  <p className="text-[11px] text-muted-foreground">Database</p>
                </div>
                <div>
                  <p className="text-lg font-semibold">{formatBytes(status.backups_bytes)}</p>
                  <p className="text-[11px] text-muted-foreground">Backups</p>
                </div>
              </div>
              <Separator />
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">Disk usage</span>
                  <span className="font-medium">
                    {formatBytes(status.disk.used)} / {formatBytes(status.disk.total)} (
                    {diskUsedPct}%)
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full ${diskUsedPct > 90 ? "bg-destructive" : "bg-primary"}`}
                    style={{ width: `${Math.min(100, diskUsedPct)}%` }}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  {formatBytes(status.disk.free)} free
                </p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Automatic backups */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Automatic Backups</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Compressed archives (database + all original medical-record files) saved to the server.
            Restorable by stopping the service, restoring <code>health.db</code> and the{" "}
            <code>attachments/</code> folder, then restarting.
          </p>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Schedule</Label>
              <Select
                value={featureSettings?.backup_schedule ?? "off"}
                onValueChange={(v) =>
                  onUpdateSetting("backup_schedule", v as FeatureSettings["backup_schedule"])
                }
                disabled={!featureSettings}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">Off (manual only)</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Keep last (archives)</Label>
              <Input
                type="number"
                min={1}
                max={100}
                className="h-9"
                value={keepMaxDraft}
                onChange={(e) => setKeepMaxDraft(e.target.value)}
                onBlur={commitKeepMax}
                disabled={!featureSettings}
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Last backup: {formatDate(status?.last_run)}
            {featureSettings && featureSettings.backup_schedule !== "off" && (
              <> · Runs {SCHEDULE_LABELS[featureSettings.backup_schedule].toLowerCase()}</>
            )}
          </p>
        </CardContent>
      </Card>

      {/* Manual backup + archives */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Backup Archives</CardTitle>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 text-xs"
                onClick={refresh}
                disabled={loading}
              >
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button
                size="sm"
                className="h-7 gap-1.5 text-xs"
                onClick={handleRunBackup}
                disabled={running}
              >
                {running ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                {running ? "Backing up…" : "Back up now"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {archives.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">
              No archives yet. Click “Back up now” to create one.
            </p>
          ) : (
            <div className="space-y-1">
              {archives.map((a) => (
                <div
                  key={a.name}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border text-xs"
                >
                  <span className="font-medium flex-1 truncate">{a.name}</span>
                  <span className="text-muted-foreground">{formatBytes(a.size_bytes)}</span>
                  <span className="text-muted-foreground/70 hidden sm:inline">
                    {formatDate(a.created_at)}
                  </span>
                  <a
                    href={backupArchiveDownloadUrl(a.name)}
                    className="p-1 text-muted-foreground hover:text-foreground"
                    title="Download"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </a>
                  <button
                    onClick={() => handleDelete(a.name)}
                    disabled={deleting === a.name}
                    className="p-1 text-muted-foreground hover:text-destructive disabled:opacity-50"
                    title="Delete"
                  >
                    {deleting === a.name ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Export / Import (household-scoped ZIP) */}
      <BackupRestoreSection />

      {/* Danger zone */}
      <Separator className="my-2" />
      <Card className="border-destructive/40">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm text-destructive">Danger Zone</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Reset Database</p>
              <p className="text-xs text-muted-foreground">
                Permanently delete all data and start fresh. Your account will be preserved.
              </p>
            </div>
            <ResetDatabaseDialog />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
