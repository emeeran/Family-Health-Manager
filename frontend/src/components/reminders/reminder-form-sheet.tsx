import useSWR from "swr";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ReminderForm } from "@/components/reminders/reminder-form";
import { createReminder } from "@/lib/api/reminders";
import { listMembers } from "@/lib/api/members";
import { mutate } from "swr";
import type { ReminderCreate } from "@/lib/types/reminder";
import type { ReminderType, ScheduleType } from "@/lib/types/enums";

interface ReminderFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReminderFormSheet({ open, onOpenChange }: ReminderFormSheetProps) {
  const { data: members = [] } = useSWR("members", async () => {
    return listMembers().catch(() => []);
  });

  async function action(prevState: unknown, formData: FormData) {
    const data: ReminderCreate = {
      family_member_id: (formData.get("family_member_id") as string) || null,
      reminder_type: formData.get("reminder_type") as ReminderType,
      title: formData.get("title") as string,
      description: (formData.get("description") as string) || null,
      schedule_type: formData.get("schedule_type") as ScheduleType,
      schedule_interval: formData.get("schedule_interval")
        ? Number(formData.get("schedule_interval"))
        : null,
      start_datetime: formData.get("start_datetime") as string,
      end_datetime: (formData.get("end_datetime") as string) || null,
    };
    try {
      await createReminder(data);
      mutate("reminders-page");
      mutate("dashboard");
      onOpenChange(false);
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create reminder" };
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>New Reminder</SheetTitle>
          <SheetDescription>Create a health reminder.</SheetDescription>
        </SheetHeader>
        <div className="mt-4">
          <ReminderForm action={action} members={members} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
