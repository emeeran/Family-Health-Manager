import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { Plus, CalendarClock, Trash2, Clock, Edit, AlertCircle, User } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { REMINDER_TYPE_LABELS } from "@/lib/constants";
import { deleteReminder } from "@/lib/api/reminders";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import type { ReminderResponse } from "@/lib/types/reminder";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { ReminderType } from "@/lib/types/enums";

interface RemindersContentProps {
  reminders: ReminderResponse[];
  members: FamilyMemberResponse[];
}

export function RemindersContent({ reminders, members }: RemindersContentProps) {
  const { mutate } = useSWRConfig();
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");

  const memberMap = useMemo(() => {
    const map = new Map<string, string>();
    members.forEach((m) => map.set(m.id, `${m.first_name} ${m.last_name}`));
    return map;
  }, [members]);

  const filtered = useMemo(() => {
    return reminders.filter((r) => {
      if (typeFilter && r.reminder_type !== typeFilter) return false;
      if (statusFilter === "active" && !r.is_active) return false;
      if (statusFilter === "inactive" && r.is_active) return false;
      return true;
    });
  }, [reminders, typeFilter, statusFilter]);

  async function handleDelete() {
    try {
      await deleteReminder(deleteId);
      toast.success("Reminder deleted");
      setDeleteOpen(false);
      await Promise.all([mutate("reminders-page"), mutate("dashboard")]);
    } catch {
      toast.error("Failed to delete reminder");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Reminders</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {reminders.filter((r) => r.is_active).length} active reminder
            {reminders.filter((r) => r.is_active).length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link to="/reminders/new">
          <Button className="shadow-sm">
            <Plus className="h-4 w-4 mr-1.5" />
            New Reminder
          </Button>
        </Link>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-end">
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">Type</Label>
          <Select
            value={typeFilter}
            onValueChange={(v) => setTypeFilter(v === "__all__" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="h-9 w-36">
              <SelectValue placeholder="All types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All types</SelectItem>
              {(Object.entries(REMINDER_TYPE_LABELS) as [ReminderType, string][]).map(
                ([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                )
              )}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">Status</Label>
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v === "__all__" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="h-9 w-28">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500/10 to-orange-500/10">
              <CalendarClock className="h-8 w-8 text-amber-500" />
            </div>
          }
          title="No reminders found"
          description={
            reminders.length === 0 ? "Create your first reminder." : "Try adjusting your filters."
          }
          action={
            reminders.length === 0 ? (
              <Link to="/reminders/new">
                <Button className="shadow-sm">Create First Reminder</Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-2">
          {filtered.map((reminder) => {
            const isOverdue = reminder.is_active && new Date(reminder.start_datetime) < new Date();
            const memberName = reminder.family_member_id
              ? memberMap.get(reminder.family_member_id)
              : null;

            return (
              <Card
                key={reminder.id}
                className={`group hover:shadow-md transition-all duration-200 ${
                  isOverdue ? "border-l-4 border-l-amber-500" : "border-l-4 border-l-transparent"
                }`}
              >
                <CardContent className="pt-3.5 pb-3.5">
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                        isOverdue
                          ? "bg-amber-500/10 text-amber-600"
                          : reminder.is_active
                            ? "bg-primary/10 text-primary"
                            : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {isOverdue ? (
                        <AlertCircle className="h-4 w-4" />
                      ) : (
                        <Clock className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className="font-medium text-sm">{reminder.title}</p>
                        <Badge
                          variant={reminder.is_active ? "default" : "secondary"}
                          className="text-[10px]"
                        >
                          {reminder.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </div>
                      {reminder.description && (
                        <p className="text-sm text-muted-foreground line-clamp-1">
                          {reminder.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {new Date(reminder.start_datetime).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        {memberName && (
                          <span className="flex items-center gap-1">
                            <User className="h-3 w-3" />
                            {memberName}
                          </span>
                        )}
                        <Badge variant="outline" className="text-[10px] py-0">
                          {REMINDER_TYPE_LABELS[reminder.reminder_type]}
                        </Badge>
                      </div>
                    </div>
                    <div className="flex gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Link to={`/reminders/${reminder.id}/edit`}>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <Edit className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => {
                          setDeleteId(reminder.id);
                          setDeleteOpen(true);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Reminder"
        description="Are you sure you want to delete this reminder?"
        onConfirm={handleDelete}
      />
    </div>
  );
}
