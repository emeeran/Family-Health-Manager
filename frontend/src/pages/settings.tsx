import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getHousehold, updateHousehold, resetDatabase } from "@/lib/api/household";
import { getMe, changePassword } from "@/lib/api/auth";
import { PasswordInput } from "@/components/shared/password-input";
import { BackupRestoreSection } from "@/components/content/backup-restore";
import { toast } from "sonner";

export default function SettingsPage() {
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

  useEffect(() => {
    async function load() {
      try {
        const [household, user] = await Promise.all([getHousehold(), getMe()]);
        setHouseholdName(household.name);
        setOriginalName(household.name);
        setUsername(user.username);
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
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

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
                <Button type="submit" size="sm" disabled={saving || householdName === originalName}>
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
  );
}

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
