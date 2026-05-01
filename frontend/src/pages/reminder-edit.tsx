import useSWR, { mutate } from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getReminder } from "@/lib/api/reminders";
import { listMembers } from "@/lib/api/members";
import { updateReminder } from "@/lib/api/reminders";
import { ReminderForm } from "@/components/reminders/reminder-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { ReminderUpdate } from "@/lib/types/reminder";
import type { ScheduleType } from "@/lib/types/enums";
import { ErrorState } from "@/components/shared/error-state";

export default function EditReminderPage() {
  const { reminderId } = useParams<{ reminderId: string }>();
  const navigate = useNavigate();

  const {
    data,
    error,
    mutate: _revalidate,
  } = useSWR(reminderId ? `reminder-${reminderId}` : null, async () => {
    const [reminder, members] = await Promise.all([getReminder(reminderId!), listMembers()]);
    return { reminder, members };
  });

  function createAction(rid: string) {
    return async function (prevState: unknown, formData: FormData) {
      const data: ReminderUpdate = {
        title: (formData.get("title") as string) || null,
        description: (formData.get("description") as string) || null,
        schedule_type: (formData.get("schedule_type") as ScheduleType) || null,
        schedule_interval: formData.get("schedule_interval")
          ? Number(formData.get("schedule_interval"))
          : null,
        start_datetime: (formData.get("start_datetime") as string) || null,
        end_datetime: (formData.get("end_datetime") as string) || null,
      };
      try {
        await updateReminder(rid, data);
        mutate(`reminder-${rid}`);
        navigate("/reminders");
        return null;
      } catch (e) {
        return { error: e instanceof Error ? e.message : "Failed to update reminder" };
      }
    };
  }

  if (error) return <ErrorState onRetry={() => _revalidate()} />;
  if (!data || !reminderId)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  const action = createAction(reminderId);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/reminders" className="hover:underline">
          Reminders
        </Link>
        <span>/</span>
        <span>{data.reminder.title}</span>
        <span>/</span>
        <h1 className="text-2xl font-bold text-foreground">Edit</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Edit Reminder</CardTitle>
        </CardHeader>
        <CardContent>
          <ReminderForm action={action} members={data.members} reminder={data.reminder} />
        </CardContent>
      </Card>
    </div>
  );
}
