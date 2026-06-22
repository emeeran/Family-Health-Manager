/** Danger-zone "Reset Database" dialog (used by the Data tab). */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/shared/password-input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { resetDatabase } from "@/lib/api/household";
import { toast } from "sonner";

export function ResetDatabaseDialog() {
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
