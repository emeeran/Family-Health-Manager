import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { getHousehold, updateHousehold } from "@/lib/api/household";
import { getMe } from "@/lib/api/auth";
import { BackupRestoreSection } from "@/components/content/backup-restore";
import { toast } from "sonner";

export default function SettingsPage() {
  const [householdName, setHouseholdName] = useState("");
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [originalName, setOriginalName] = useState("");

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

      <Card className="opacity-60">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Change Password</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            This feature is coming soon. Contact your administrator to reset your password.
          </p>
        </CardContent>
      </Card>

      <BackupRestoreSection />
    </div>
  );
}
