import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { listMembers } from "@/lib/api/members";
import { createReminder } from "@/lib/api/reminders";
import { ReminderForm } from "@/components/reminders/reminder-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { ReminderCreate } from "@/lib/types/reminder";
import type { ReminderType, ScheduleType } from "@/lib/types/enums";

export default function NewReminderPage() {
  const navigate = useNavigate();
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
      navigate("/reminders");
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create reminder" };
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link to="/reminders" className="text-sm text-muted-foreground hover:underline">
          Reminders
        </Link>
        <span className="text-sm text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">New Reminder</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Create Reminder</CardTitle>
        </CardHeader>
        <CardContent>
          <ReminderForm action={action} members={members} />
        </CardContent>
      </Card>
    </div>
  );
}
