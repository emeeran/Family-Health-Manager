"use client";

import { useActionState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { REMINDER_TYPE_LABELS, SCHEDULE_TYPE_LABELS } from "@/lib/constants";
import type { ReminderType, ScheduleType } from "@/lib/types/enums";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { ReminderResponse } from "@/lib/types/reminder";
import { Loader2 } from "lucide-react";

const reminderSchema = z.object({
  family_member_id: z.string().optional(),
  reminder_type: z.enum([
    "appointment",
    "medication",
    "follow_up",
    "check_up",
    "prescription_refill",
  ] as const),
  title: z.string().min(1, "Title is required"),
  description: z.string().optional(),
  schedule_type: z.enum(["once", "daily", "weekly", "custom"] as const),
  schedule_interval: z.number().min(1).max(365).optional(),
  start_datetime: z.string().min(1, "Start date/time is required"),
  end_datetime: z.string().optional(),
});

type ReminderFormValues = z.infer<typeof reminderSchema>;

interface ReminderFormProps {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  members: FamilyMemberResponse[];
  reminder?: ReminderResponse;
}

export function ReminderForm({ action, members, reminder }: ReminderFormProps) {
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);

  const {
    register,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ReminderFormValues>({
    resolver: zodResolver(reminderSchema),
    defaultValues: reminder
      ? {
          family_member_id: reminder.family_member_id ?? "",
          reminder_type: reminder.reminder_type,
          title: reminder.title,
          description: reminder.description ?? "",
          schedule_type: reminder.schedule_type,
          schedule_interval: reminder.schedule_interval ?? undefined,
          start_datetime: reminder.start_datetime.slice(0, 16),
          end_datetime: reminder.end_datetime ? reminder.end_datetime.slice(0, 16) : "",
        }
      : {
          family_member_id: "",
          reminder_type: undefined,
          title: "",
          description: "",
          schedule_type: undefined,
          schedule_interval: undefined,
          start_datetime: "",
          end_datetime: "",
        },
  });

  const reminderType = watch("reminder_type");
  const scheduleType = watch("schedule_type");
  const familyMemberId = watch("family_member_id");

  return (
    <form action={formAction} className="space-y-4 max-w-2xl">
      {Boolean(
        state && typeof state === "object" && "error" in (state as Record<string, unknown>)
      ) && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {String((state as Record<string, unknown>).error ?? "Unknown error")}
        </div>
      )}

      {/* Type & Schedule */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Reminder Details
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-xs">Reminder Type</Label>
            <input type="hidden" name="reminder_type" value={reminderType ?? ""} />
            <Select
              value={reminderType ?? ""}
              onValueChange={(v) => {
                if (v) setValue("reminder_type", v as ReminderType);
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(REMINDER_TYPE_LABELS) as [ReminderType, string][]).map(
                  ([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
            {errors.reminder_type && (
              <p className="text-[11px] text-destructive">{errors.reminder_type.message}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Schedule</Label>
            <input type="hidden" name="schedule_type" value={scheduleType ?? ""} />
            <Select
              value={scheduleType ?? ""}
              onValueChange={(v) => {
                if (v) setValue("schedule_type", v as ScheduleType);
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select schedule" />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(SCHEDULE_TYPE_LABELS) as [ScheduleType, string][]).map(
                  ([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
            {errors.schedule_type && (
              <p className="text-[11px] text-destructive">{errors.schedule_type.message}</p>
            )}
          </div>
        </div>

        {scheduleType === "custom" && (
          <div className="space-y-1 max-w-32">
            <Label htmlFor="schedule_interval" className="text-xs">
              Interval (days)
            </Label>
            <Input
              id="schedule_interval"
              type="number"
              min={1}
              max={365}
              {...register("schedule_interval", { valueAsNumber: true })}
              className="h-9"
            />
          </div>
        )}
      </div>

      {/* Title & Description */}
      <div className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="title" className="text-xs">
            Title
          </Label>
          <Input id="title" {...register("title")} placeholder="Reminder title" className="h-9" />
          {errors.title && <p className="text-[11px] text-destructive">{errors.title.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="description" className="text-xs">
            Description (optional)
          </Label>
          <Textarea
            id="description"
            {...register("description")}
            rows={2}
            placeholder="Additional details"
            className="text-sm min-h-[52px]"
          />
        </div>
      </div>

      {/* Assignment & Timing */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          When & Who
        </p>
        <div className="space-y-1">
          <Label className="text-xs">Family Member (optional)</Label>
          <input type="hidden" name="family_member_id" value={familyMemberId ?? ""} />
          <Select
            value={familyMemberId ?? ""}
            onValueChange={(v) => setValue("family_member_id", v ?? "")}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="All members" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">All members</SelectItem>
              {members.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.first_name} {m.last_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="start_datetime" className="text-xs">
              Start
            </Label>
            <Input
              id="start_datetime"
              type="datetime-local"
              {...register("start_datetime")}
              className="h-9"
            />
            {errors.start_datetime && (
              <p className="text-[11px] text-destructive">{errors.start_datetime.message}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="end_datetime" className="text-xs">
              End (optional)
            </Label>
            <Input
              id="end_datetime"
              type="datetime-local"
              {...register("end_datetime")}
              className="h-9"
            />
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Button type="submit" disabled={isPending} size="sm">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {isPending ? "Saving..." : reminder ? "Update Reminder" : "Create Reminder"}
        </Button>
      </div>
    </form>
  );
}
