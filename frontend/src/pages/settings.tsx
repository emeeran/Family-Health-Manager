import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { getHousehold, updateHousehold, getSettings, updateSettings } from "@/lib/api/household";
import { getMe, changePassword } from "@/lib/api/auth";
import { ApiError } from "@/lib/api-client";
import { PasswordInput } from "@/components/shared/password-input";
import { DataTab } from "@/components/content/data-tab";
import { getAIStatus, type ProviderStatus } from "@/lib/api/ai";
import {
  getAIProviderConfig,
  updateAIProviderConfig,
  fetchProviderModels,
  getProviderKeys,
  updateProviderKey,
  deleteProviderKey,
  importProviderKeysFromEnv,
} from "@/lib/api/household";
import type {
  ProviderConfigItem,
  AIProviderConfigResponse,
  ProviderKeyStatus,
} from "@/lib/types/household";
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
  KeyRound,
  Trash2,
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

type TabId = "general" | "features" | "data" | "ai-providers";

const VALID_TABS = new Set<string>(["general", "features", "data", "ai-providers"]);

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "features", label: "Features" },
  { id: "data", label: "Data" },
  { id: "ai-providers", label: "AI Providers" },
];

// ── Feature definitions ────────────────────────────────────────

type BooleanFeatureKey = Extract<
  keyof FeatureSettings,
  "ai_features" | "ai_verification" | "notifications" | "email_notifications" | "smart_entry"
>;

const FEATURE_DEFS: {
  key: BooleanFeatureKey;
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

  /** Generic settings updater (used by the Data tab for non-boolean fields). */
  const updateSetting = useCallback(
    async <K extends keyof FeatureSettings>(key: K, value: FeatureSettings[K]) => {
      if (!featureSettings) return;
      const updated = { ...featureSettings, [key]: value };
      setFeatureSettings(updated);
      try {
        await updateSettings({ settings: updated });
      } catch {
        setFeatureSettings(featureSettings); // rollback
        toast.error("Failed to update setting");
      }
    },
    [featureSettings]
  );

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

      {activeTab === "data" && (
        <DataTab featureSettings={featureSettings} onUpdateSetting={updateSetting} />
      )}

      {activeTab === "ai-providers" && <AIProvidersTab />}
    </div>
  );
}

// ── AI Providers Tab ──────────────────────────────────────────

function AIProvidersTab() {
  // Config state
  const [config, setConfig] = useState<AIProviderConfigResponse | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Fetched models state — tracks which scope is fetching ("__all__" or a provider id)
  const [fetchedModels, setFetchedModels] = useState<Record<string, string[]> | null>(null);
  const [fetchingModels, setFetchingModels] = useState<string | null>(null);

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

  async function saveConfig(
    providers: ProviderConfigItem[],
    primaryProvider?: "cloud" | "local",
    geminiAuth?: "auto" | "adc" | "api_key"
  ) {
    if (!config) return;
    const primary_provider = primaryProvider ?? config.config.primary_provider;
    const gemini_auth = geminiAuth ?? config.config.gemini_auth ?? "auto";
    setSaving(true);
    try {
      const result = await updateAIProviderConfig({ providers, primary_provider, gemini_auth });
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

  async function fetchModels(provider?: string) {
    const scope = provider ?? "__all__";
    setFetchingModels(scope);
    try {
      const result = await fetchProviderModels(provider);
      // Merge so a single-provider refresh doesn't discard the others.
      setFetchedModels((prev) => ({ ...(prev ?? {}), ...result.models }));
      toast.success("Models refreshed");
    } catch {
      toast.error("Failed to fetch models");
    } finally {
      setFetchingModels((f) => (f === scope ? null : f));
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
    setConfig({ ...config, config: { ...config.config, providers: updated } });
    saveConfig(updated);
  }

  function handleModelChange(index: number, model: string) {
    if (!config) return;
    const updated = config.config.providers.map((p, i) => (i === index ? { ...p, model } : p));
    setConfig({ ...config, config: { ...config.config, providers: updated } });
    saveConfig(updated);
  }

  function handleMoveUp(index: number) {
    if (index === 0 || !config) return;
    const arr = [...config.config.providers];
    [arr[index - 1], arr[index]] = [arr[index], arr[index - 1]];
    setConfig({ ...config, config: { ...config.config, providers: arr } });
    saveConfig(arr);
  }

  function handleMoveDown(index: number) {
    if (!config || index >= config.config.providers.length - 1) return;
    const arr = [...config.config.providers];
    [arr[index], arr[index + 1]] = [arr[index + 1], arr[index]];
    setConfig({ ...config, config: { ...config.config, providers: arr } });
    saveConfig(arr);
  }

  function handlePrimaryChange(primaryProvider: "cloud" | "local") {
    if (!config) return;
    setConfig({
      ...config,
      config: { ...config.config, primary_provider: primaryProvider },
    });
    saveConfig(config.config.providers, primaryProvider);
  }

  function handleGeminiAuthChange(auth: "auto" | "adc" | "api_key") {
    if (!config) return;
    setConfig({ ...config, config: { ...config.config, gemini_auth: auth } });
    saveConfig(config.config.providers, undefined, auth);
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
    <div className="space-y-4 pt-2">
      {/* API Keys — admin-managed, encrypted at rest. Live status is tied to
          each key here and re-checked whenever a key changes. */}
      <ProviderKeysCard statusMap={statusMap} onStatusRefresh={fetchStatus} />

      {/* Primary provider — Cloud vs Local */}
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">Primary provider</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Tried first; the other is used as automatic fallback.
          </p>
        </div>
        <div className="inline-flex items-center rounded-md border border-border bg-muted/40 p-0.5">
          {(["local", "cloud"] as const).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => handlePrimaryChange(opt)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                config.config.primary_provider === opt
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {opt === "local" ? "Local" : "Cloud"}
            </button>
          ))}
        </div>
      </div>

      {/* Gemini authentication — ADC (Vertex) vs API Key vs Auto */}
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">Gemini authentication</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            How Gemini authenticates. ADC routes through Vertex AI using server credentials.
            {!config.adc_available && (
              <span className="text-amber-600 dark:text-amber-400">
                {" "}
                · ADC is not configured on this server (no credentials file or Vertex project), so
                it will fall back to the API key.
              </span>
            )}
          </p>
        </div>
        <Select
          value={config.config.gemini_auth ?? "auto"}
          onValueChange={(v) => handleGeminiAuthChange(v as "auto" | "adc" | "api_key")}
        >
          <SelectTrigger className="h-8 w-[150px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Auto</SelectItem>
            <SelectItem value="adc" disabled={!config.adc_available}>
              ADC (Vertex)
            </SelectItem>
            <SelectItem value="api_key">API Key</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Section A: Provider Configuration */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-sm font-medium">Provider Configuration</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Reorder to set fallback priority. Top provider is tried first.
              {checkedAt && (
                <span className="text-muted-foreground/60">
                  {" · "}Status checked{" "}
                  {Math.round((Date.now() - checkedAt.getTime()) / 1000) < 60
                    ? "just now"
                    : `${Math.round((Date.now() - checkedAt.getTime()) / 60000)}m ago`}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
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
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 text-xs"
              onClick={() => fetchModels()}
              disabled={fetchingModels === "__all__"}
            >
              <RefreshCw
                className={`h-3 w-3 ${fetchingModels === "__all__" ? "animate-spin" : ""}`}
              />
              Refresh Models
            </Button>
            {saving && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> Saving...
              </span>
            )}
          </div>
        </div>

        <div className="space-y-2">
          {providers.map((prov, i) => {
            // Prefer fetched models, fall back to static models
            const providerModels = fetchedModels?.[prov.id]?.length
              ? fetchedModels[prov.id]
              : models[prov.id] || [];
            return (
              <ProviderConfigRow
                key={prov.id}
                provider={prov}
                label={labels[prov.id] || prov.id}
                availableModels={providerModels}
                isFirst={i === 0}
                isLast={i === providers.length - 1}
                status={statusMap.get(prov.id)}
                refreshingModels={fetchingModels === prov.id}
                onRefreshModels={() => fetchModels(prov.id)}
                onToggle={(enabled) => handleToggle(i, enabled)}
                onModelChange={(model) => handleModelChange(i, model)}
                onMoveUp={() => handleMoveUp(i)}
                onMoveDown={() => handleMoveDown(i)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── API Keys Card (admin) ──

function ProviderKeysCard({
  statusMap,
  onStatusRefresh,
}: {
  statusMap: Map<string, ProviderStatus>;
  onStatusRefresh: () => void;
}) {
  const [keys, setKeys] = useState<ProviderKeyStatus[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmImport, setConfirmImport] = useState(false);

  const loadKeys = useCallback(() => {
    setLoading(true);
    getProviderKeys()
      .then((r) => {
        setKeys(r.keys);
        setForbidden(false);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          setForbidden(true); // non-admin — card is hidden below
        } else {
          toast.error("Failed to load API keys");
        }
        setKeys(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  // Non-admins see nothing; everyone else gets a brief loader.
  if (forbidden) return null;
  if (loading || !keys) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-6">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Loading API keys…</span>
        </CardContent>
      </Card>
    );
  }

  async function save(provider: string) {
    const value = draft.trim();
    if (!value) return;
    setBusy(provider);
    try {
      await updateProviderKey(provider, value);
      toast.success("API key saved");
      setEditing(null);
      setDraft("");
      loadKeys();
      onStatusRefresh();
    } catch {
      toast.error("Failed to save API key");
    } finally {
      setBusy(null);
    }
  }

  async function clearKey(provider: string) {
    setBusy(provider);
    try {
      await deleteProviderKey(provider);
      toast.success("API key cleared");
      loadKeys();
      onStatusRefresh();
    } catch {
      toast.error("Failed to clear API key");
    } finally {
      setBusy(null);
    }
  }

  async function doImport() {
    setBusy("__import__");
    try {
      const r = await importProviderKeysFromEnv();
      const msg =
        r.imported.length > 0
          ? `Imported ${r.imported.length} key(s) from .env`
          : "No keys found in .env";
      toast.success(r.skipped.length ? `${msg} (${r.skipped.length} empty)` : msg);
      setConfirmImport(false);
      loadKeys();
      onStatusRefresh();
    } catch {
      toast.error("Import from .env failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <KeyRound className="h-4 w-4" /> API Keys
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Stored encrypted. Overrides any value in <code>.env</code>; use Import to migrate.
            </p>
          </div>
          {confirmImport ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground hidden sm:inline">
                Overwrites saved keys
              </span>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => setConfirmImport(false)}
                disabled={!!busy}
              >
                Cancel
              </Button>
              <Button size="sm" className="h-7 text-xs" onClick={doImport} disabled={!!busy}>
                {busy === "__import__" ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Confirm Import"
                )}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 text-xs"
              onClick={() => setConfirmImport(true)}
              disabled={!!busy}
            >
              Import from .env
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {keys.map((k) => {
          const isEditing = editing === k.provider;
          return (
            <div
              key={k.provider}
              className="flex flex-col gap-2 rounded-lg border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium">{k.label}</div>
                <div className="text-xs text-muted-foreground">
                  {k.is_set ? (
                    <span className="text-emerald-600">
                      Configured{k.masked ? ` · ${k.masked}` : ""}
                    </span>
                  ) : k.using_env ? (
                    <span className="text-amber-600">
                      Using .env{k.masked ? ` · ${k.masked}` : ""}
                    </span>
                  ) : (
                    <span>Not set</span>
                  )}
                </div>
                {(() => {
                  const st = statusMap.get(k.provider);
                  if (!st) return null;
                  return (
                    <div
                      className={`mt-0.5 flex items-center gap-1 text-[11px] ${
                        st.available ? "text-emerald-600" : "text-red-500"
                      }`}
                    >
                      {st.available ? (
                        <CheckCircle2 className="h-3 w-3 shrink-0" />
                      ) : (
                        <XCircle className="h-3 w-3 shrink-0" />
                      )}
                      <span className="truncate">
                        {st.available
                          ? `Connected${st.response_ms != null ? ` · ${st.response_ms}ms` : ""}`
                          : st.error || "Unavailable"}
                      </span>
                    </div>
                  );
                })()}
              </div>

              <div className="flex items-center gap-2">
                {isEditing ? (
                  <>
                    {k.is_secret ? (
                      <PasswordInput
                        autoFocus
                        className="h-8 w-56 text-sm"
                        placeholder={k.is_set ? "Enter new key to replace" : "Paste API key"}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") save(k.provider);
                          if (e.key === "Escape") {
                            setEditing(null);
                            setDraft("");
                          }
                        }}
                      />
                    ) : (
                      <Input
                        autoFocus
                        className="h-8 w-56 text-sm"
                        placeholder="http://localhost:11434"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") save(k.provider);
                          if (e.key === "Escape") {
                            setEditing(null);
                            setDraft("");
                          }
                        }}
                      />
                    )}
                    <Button
                      size="sm"
                      className="h-8"
                      onClick={() => save(k.provider)}
                      disabled={!!busy || !draft.trim()}
                    >
                      {busy === k.provider ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        "Save"
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8"
                      onClick={() => {
                        setEditing(null);
                        setDraft("");
                      }}
                      disabled={!!busy}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 text-xs"
                      onClick={() => {
                        setEditing(k.provider);
                        setDraft(k.is_secret ? "" : (k.masked ?? ""));
                      }}
                      disabled={!!busy}
                    >
                      <KeyRound className="h-3 w-3" />
                      {k.is_set ? "Edit" : "Set"}
                    </Button>
                    {k.is_set && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 text-xs text-muted-foreground hover:text-destructive"
                        onClick={() => clearKey(k.provider)}
                        disabled={!!busy}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
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
  refreshingModels,
  onRefreshModels,
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
  refreshingModels: boolean;
  onRefreshModels: () => void;
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

      {/* Status dot — tooltip shows response time or the error */}
      {status ? (
        <span
          className="flex items-center gap-1 shrink-0"
          title={
            status.available
              ? status.response_ms != null
                ? `Connected · ${status.response_ms}ms`
                : "Connected"
              : status.error || "Unavailable"
          }
        >
          {status.available ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-red-400" />
          )}
          {status.available && status.response_ms != null && (
            <span className="text-[10px] text-emerald-600/80 tabular-nums">
              {status.response_ms}ms
            </span>
          )}
        </span>
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

      {/* Per-provider model refresh */}
      <Button
        size="sm"
        variant="ghost"
        className="h-7 w-7 shrink-0 p-0"
        onClick={onRefreshModels}
        disabled={refreshingModels}
        title="Refresh models for this provider"
      >
        <RefreshCw className={`h-3 w-3 ${refreshingModels ? "animate-spin" : ""}`} />
      </Button>

      {/* Enable toggle */}
      <Switch size="sm" checked={provider.enabled} onCheckedChange={onToggle} />
    </div>
  );
}
