import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getHousehold,
  updateHousehold,
  resetDatabase,
  getSettings,
  updateSettings,
} from "@/lib/api/household";
import { getMe, changePassword } from "@/lib/api/auth";
import { PasswordInput } from "@/components/shared/password-input";
import { BackupRestoreSection } from "@/components/content/backup-restore";
import { getAIStatus, type ProviderStatus } from "@/lib/api/ai";
import { getAIProviderConfig, updateAIProviderConfig } from "@/lib/api/household";
import type { ProviderConfigItem, AIProviderConfigResponse } from "@/lib/types/household";
import { toast } from "sonner";
import {
  CheckCircle2,
  XCircle,
  RefreshCw,
  Loader2,
  Wifi,
  WifiOff,
  ChevronUp,
  ChevronDown,
  GripVertical,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FeatureSettings } from "@/lib/types/household";

// ── Tab configuration ──────────────────────────────────────────

type TabId = "general" | "features" | "ai-providers";

const VALID_TABS = new Set<string>(["general", "features", "ai-providers"]);

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "features", label: "Features" },
  { id: "ai-providers", label: "AI Providers" },
];

// ── Feature definitions ────────────────────────────────────────

const FEATURE_DEFS: {
  key: keyof FeatureSettings;
  label: string;
  description: string;
}[] = [
  {
    key: "ai_features",
    label: "AI Features",
    description: "AI-powered chat, insights, and document extraction",
  },
  {
    key: "ai_verification",
    label: "AI Verification",
    description: "Automatically verify AI responses for accuracy",
  },
  {
    key: "notifications",
    label: "Notifications",
    description: "In-app notifications and appointment reminders",
  },
  {
    key: "email_notifications",
    label: "Email Notifications",
    description: "Receive notifications and reminders via email (requires SMTP setup)",
  },
  {
    key: "smart_entry",
    label: "Smart Entry",
    description: "AI-assisted quick record creation from natural language",
  },
];

// ── Main page ──────────────────────────────────────────────────

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab") || "general";
  const activeTab: TabId = VALID_TABS.has(rawTab) ? (rawTab as TabId) : "general";

  const handleTabChange = useCallback(
    (tab: TabId) => {
      setSearchParams(tab === "general" ? {} : { tab }, { replace: true });
    },
    [setSearchParams]
  );

  const [householdName, setHouseholdName] = useState("");
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [originalName, setOriginalName] = useState("");

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  // Feature settings state
  const [featureSettings, setFeatureSettings] = useState<FeatureSettings | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [household, user, settingsResp] = await Promise.all([
          getHousehold(),
          getMe(),
          getSettings(),
        ]);
        setHouseholdName(household.name);
        setOriginalName(household.name);
        setUsername(user.username);
        setFeatureSettings(settingsResp.settings);
      } catch {
        toast.error("Failed to load settings");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSaveHousehold(e: React.FormEvent) {
    e.preventDefault();
    if (!householdName.trim()) return;
    setSaving(true);
    try {
      await updateHousehold({ name: householdName.trim() });
      setOriginalName(householdName.trim());
      toast.success("Household name updated");
    } catch {
      toast.error("Failed to save household name");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      toast.success("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to change password";
      toast.error(msg);
    } finally {
      setChangingPassword(false);
    }
  }

  async function handleToggle(key: keyof FeatureSettings, value: boolean) {
    if (!featureSettings) return;
    const updated = { ...featureSettings, [key]: value };
    setFeatureSettings(updated);
    try {
      await updateSettings({ settings: updated });
      toast.success("Setting updated");
    } catch {
      // Revert on failure
      setFeatureSettings(featureSettings);
      toast.error("Failed to update setting");
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-7 w-24" />
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-24" />
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Skeleton className="h-8 flex-1" />
              <Skeleton className="h-8 w-16" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-20" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-4 w-32" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b pb-0">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`
                inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium
                border-b-2 transition-colors cursor-pointer
                ${
                  isActive
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                }
              `}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {activeTab === "general" && (
        <div className="space-y-6 pt-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Household</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveHousehold} className="space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="household_name" className="text-xs">
                    Household Name
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id="household_name"
                      value={householdName}
                      onChange={(e) => setHouseholdName(e.target.value)}
                      className="h-9"
                    />
                    <Button
                      type="submit"
                      size="sm"
                      disabled={saving || householdName === originalName}
                    >
                      {saving ? "Saving..." : "Save"}
                    </Button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Account</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <span className="text-xs text-muted-foreground">Username:</span>{" "}
                <span className="text-sm font-medium">{username}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Change Password</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleChangePassword} className="space-y-3 max-w-md">
                <div className="space-y-1">
                  <Label htmlFor="current_password" className="text-xs">
                    Current Password
                  </Label>
                  <PasswordInput
                    id="current_password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="h-9"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="new_password" className="text-xs">
                    New Password
                  </Label>
                  <PasswordInput
                    id="new_password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="h-9"
                    required
                    minLength={8}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    At least 8 characters with uppercase, digit, and special character.
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="confirm_password" className="text-xs">
                    Confirm New Password
                  </Label>
                  <PasswordInput
                    id="confirm_password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="h-9"
                    required
                    minLength={8}
                  />
                  {confirmPassword && newPassword !== confirmPassword && (
                    <p className="text-[11px] text-destructive">Passwords do not match</p>
                  )}
                </div>
                <Button
                  type="submit"
                  size="sm"
                  disabled={
                    changingPassword ||
                    !currentPassword ||
                    !newPassword ||
                    !confirmPassword ||
                    newPassword !== confirmPassword
                  }
                >
                  {changingPassword ? "Changing..." : "Change Password"}
                </Button>
              </form>
            </CardContent>
          </Card>

          <BackupRestoreSection />

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
      )}

      {activeTab === "features" && (
        <div className="space-y-4 pt-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Feature Toggles</CardTitle>
            </CardHeader>
            <CardContent className="space-y-0">
              {featureSettings &&
                FEATURE_DEFS.map((feat, i) => (
                  <div key={feat.key}>
                    <div className="flex items-center justify-between py-3">
                      <div className="pr-4">
                        <p className="text-sm font-medium">{feat.label}</p>
                        <p className="text-xs text-muted-foreground">{feat.description}</p>
                      </div>
                      <Switch
                        size="sm"
                        checked={featureSettings[feat.key]}
                        onCheckedChange={(val: boolean) => handleToggle(feat.key, val)}
                      />
                    </div>
                    {i < FEATURE_DEFS.length - 1 && <Separator />}
                  </div>
                ))}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "ai-providers" && <AIProvidersTab />}
    </div>
  );
}

// ── Reset Database Dialog ──────────────────────────────────────

function ResetDatabaseDialog() {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [resetting, setResetting] = useState(false);

  function handleOpenChange(val: boolean) {
    setOpen(val);
    if (!val) {
      setPassword("");
      setConfirmation("");
    }
  }

  async function handleReset() {
    setResetting(true);
    try {
      await resetDatabase(password, confirmation);
      toast.success("Database reset successfully. Refreshing...");
      setOpen(false);
      setPassword("");
      setConfirmation("");
      setTimeout(() => window.location.reload(), 1500);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to reset database";
      toast.error(msg);
    } finally {
      setResetting(false);
    }
  }

  const confirmed = confirmation === "RESET" && password.length > 0;

  return (
    <>
      <Button variant="destructive" size="sm" onClick={() => setOpen(true)}>
        Reset Database
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Database</DialogTitle>
            <DialogDescription>
              This will permanently delete all members, health records, providers, attachments,
              conversations, reminders, and notifications. This action cannot be undone. Your admin
              account will be preserved.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="reset-password" className="text-xs">
                Your Password
              </Label>
              <PasswordInput
                id="reset-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password to confirm"
                className="h-9"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reset-confirmation" className="text-xs">
                Type <strong>RESET</strong> to confirm
              </Label>
              <Input
                id="reset-confirmation"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                placeholder="RESET"
                className="h-9"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={resetting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleReset} disabled={!confirmed || resetting}>
              {resetting ? "Resetting..." : "Reset Database"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── AI Providers Tab ──────────────────────────────────────────

function AIProvidersTab() {
  // Config state
  const [config, setConfig] = useState<AIProviderConfigResponse | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Status state
  const [statusProviders, setStatusProviders] = useState<ProviderStatus[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  // Load config on mount
  useEffect(() => {
    getAIProviderConfig()
      .then((result) => setConfig(result))
      .catch(() => toast.error("Failed to load provider config"))
      .finally(() => setConfigLoading(false));
  }, []);

  async function saveConfig(providers: ProviderConfigItem[]) {
    if (!config) return;
    setSaving(true);
    try {
      const result = await updateAIProviderConfig({ providers });
      setConfig(result);
    } catch {
      toast.error("Failed to save provider config");
    } finally {
      setSaving(false);
    }
  }

  async function fetchStatus() {
    setRefreshing(true);
    try {
      const result = await getAIStatus();
      setStatusProviders(result.providers);
      setCheckedAt(new Date());
    } catch {
      toast.error("Failed to check provider status");
    } finally {
      setRefreshing(false);
    }
  }

  // Auto-check status once config loads
  useEffect(() => {
    if (config) fetchStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when config loads, not on every config change
  }, [config?.config.providers.length]);

  function handleToggle(index: number, enabled: boolean) {
    if (!config) return;
    const updated = config.config.providers.map((p, i) => (i === index ? { ...p, enabled } : p));
    setConfig({ ...config, config: { providers: updated } });
    saveConfig(updated);
  }

  function handleModelChange(index: number, model: string) {
    if (!config) return;
    const updated = config.config.providers.map((p, i) => (i === index ? { ...p, model } : p));
    setConfig({ ...config, config: { providers: updated } });
    saveConfig(updated);
  }

  function handleMoveUp(index: number) {
    if (index === 0 || !config) return;
    const arr = [...config.config.providers];
    [arr[index - 1], arr[index]] = [arr[index], arr[index - 1]];
    setConfig({ ...config, config: { providers: arr } });
    saveConfig(arr);
  }

  function handleMoveDown(index: number) {
    if (!config || index >= config.config.providers.length - 1) return;
    const arr = [...config.config.providers];
    [arr[index], arr[index + 1]] = [arr[index + 1], arr[index]];
    setConfig({ ...config, config: { providers: arr } });
    saveConfig(arr);
  }

  if (configLoading) {
    return (
      <div className="space-y-4 pt-2">
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Loading provider config...</span>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!config) return null;

  const labels = config.provider_labels;
  const models = config.available_models;
  const providers = config.config.providers;

  // Build a map from provider id to status
  const statusMap = new Map(statusProviders.map((s) => [s.id ?? s.name, s]));

  return (
    <div className="space-y-6 pt-2">
      {/* Section A: Provider Configuration */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium">Provider Configuration</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Reorder to set fallback priority. Top provider is tried first.
            </p>
          </div>
          {saving && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" /> Saving...
            </span>
          )}
        </div>

        <div className="space-y-2">
          {providers.map((prov, i) => (
            <ProviderConfigRow
              key={prov.id}
              provider={prov}
              label={labels[prov.id] || prov.id}
              availableModels={models[prov.id] || []}
              isFirst={i === 0}
              isLast={i === providers.length - 1}
              status={statusMap.get(prov.id)}
              onToggle={(enabled) => handleToggle(i, enabled)}
              onModelChange={(model) => handleModelChange(i, model)}
              onMoveUp={() => handleMoveUp(i)}
              onMoveDown={() => handleMoveDown(i)}
            />
          ))}
        </div>
      </div>

      {/* Section B: Live Status */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Live Status</h3>
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1.5 text-xs"
            onClick={fetchStatus}
            disabled={refreshing}
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            Check Status
          </Button>
        </div>

        {statusProviders.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {statusProviders.map((sp) => (
              <div
                key={sp.name}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs ${
                  sp.available
                    ? "border-emerald-200 bg-emerald-50/50"
                    : "border-red-200 bg-red-50/50 opacity-70"
                }`}
              >
                {sp.available ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                )}
                <span className="font-medium flex-1">{sp.name}</span>
                {sp.available && sp.response_ms != null && (
                  <span className="text-emerald-600">{sp.response_ms}ms</span>
                )}
                {!sp.available && sp.error && (
                  <span className="text-muted-foreground truncate max-w-[120px]">{sp.error}</span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground py-4 text-center">
            Click "Check Status" to test provider connectivity.
          </p>
        )}

        {checkedAt && (
          <p className="text-[11px] text-muted-foreground/60">
            Last checked{" "}
            {Math.round((Date.now() - checkedAt.getTime()) / 1000) < 60
              ? "just now"
              : `${Math.round((Date.now() - checkedAt.getTime()) / 60000)}m ago`}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Provider Config Row ──

function ProviderConfigRow({
  provider,
  label,
  availableModels,
  isFirst,
  isLast,
  status,
  onToggle,
  onModelChange,
  onMoveUp,
  onMoveDown,
}: {
  provider: ProviderConfigItem;
  label: string;
  availableModels: string[];
  isFirst: boolean;
  isLast: boolean;
  status?: ProviderStatus;
  onToggle: (enabled: boolean) => void;
  onModelChange: (model: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const isOllama = availableModels.length === 0;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border ${provider.enabled ? "" : "opacity-60"}`}
    >
      {/* Reorder buttons */}
      <div className="flex flex-col gap-0.5 shrink-0">
        <button
          onClick={onMoveUp}
          disabled={isFirst}
          className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors"
        >
          <ChevronUp className="h-3 w-3" />
        </button>
        <button
          onClick={onMoveDown}
          disabled={isLast}
          className="p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors"
        >
          <ChevronDown className="h-3 w-3" />
        </button>
      </div>

      {/* Status dot */}
      {status ? (
        status.available ? (
          <Wifi className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
        ) : (
          <WifiOff className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />
        )
      ) : (
        <GripVertical className="h-3.5 w-3.5 text-muted-foreground/30 shrink-0" />
      )}

      {/* Provider name */}
      <span className="text-sm font-medium min-w-[100px]">{label}</span>

      {/* Model selector */}
      <div className="flex-1 min-w-0">
        {isOllama ? (
          <Input
            value={provider.model}
            onChange={(e) => onModelChange(e.target.value)}
            placeholder="Model name"
            className="h-7 text-xs"
            disabled={!provider.enabled}
          />
        ) : (
          <Select
            value={provider.model}
            onValueChange={(v) => v && onModelChange(v)}
            disabled={!provider.enabled}
          >
            <SelectTrigger className="h-7 text-xs">
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              {availableModels.map((m) => (
                <SelectItem key={m} value={m}>
                  <span className="text-xs">{m}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Enable toggle */}
      <Switch size="sm" checked={provider.enabled} onCheckedChange={onToggle} />
    </div>
  );
}
