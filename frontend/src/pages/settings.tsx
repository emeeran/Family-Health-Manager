import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { getHousehold, updateHousehold } from "@/lib/api/household";
import { getMe } from "@/lib/api/auth";
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
    if (newPassword.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }
    setChangingPassword(true);
    try {
      // TODO: Call backend password change endpoint when available
      toast.success("Password change will be available once the backend endpoint is added");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      toast.error("Failed to change password");
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
            <div className="grid gap-3 md:grid-cols-3">
              <div className="space-y-1">
                <Label htmlFor="current_password" className="text-xs">
                  Current
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
                  New
                </Label>
                <PasswordInput
                  id="new_password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="h-9"
                  required
                  minLength={6}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="confirm_password" className="text-xs">
                  Confirm
                </Label>
                <PasswordInput
                  id="confirm_password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="h-9"
                  required
                  minLength={6}
                />
              </div>
            </div>
            <Button
              type="submit"
              size="sm"
              disabled={changingPassword || !currentPassword || !newPassword || !confirmPassword}
            >
              {changingPassword ? "Changing..." : "Change Password"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <BackupRestoreSection />
    </div>
  );
}
