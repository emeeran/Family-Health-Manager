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
import { toast } from "sonner";
import type { FeatureSettings } from "@/lib/types/household";

// ── Tab configuration ──────────────────────────────────────────

type TabId = "general" | "features";

const VALID_TABS = new Set<string>(["general", "features"]);

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "features", label: "Features" },
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
