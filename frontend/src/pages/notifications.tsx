import { useState } from "react";
import { Trash2, Check, Clock, Info, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import {
  markAsRead,
  markAllAsRead,
  deleteNotification,
  listNotifications,
} from "@/lib/api/notifications";
import { useSWRConfig } from "swr";
import useSWR from "swr";
import { toast } from "sonner";
import { ErrorState } from "@/components/shared/error-state";
import type { NotificationResponse } from "@/lib/types/notification";
import { formatRelativeTime } from "@/lib/utils";

function NotificationIcon({ title }: { title: string }) {
  const lower = title.toLowerCase();
  if (lower.includes("warning") || lower.includes("alert") || lower.includes("overdue")) {
    return <AlertTriangle className="h-4 w-4 text-amber-500" />;
  }
  if (lower.includes("success") || lower.includes("completed") || lower.includes("done")) {
    return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  }
  return <Info className="h-4 w-4 text-blue-500" />;
}

function NotificationsContent({ notifications }: { notifications: NotificationResponse[] }) {
  const { mutate } = useSWRConfig();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [markingAll, setMarkingAll] = useState(false);

  async function handleMarkAsRead(id: string) {
    await markAsRead(id);
    await Promise.all([mutate("notifications"), mutate("notification-count")]);
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    try {
      const result = await markAllAsRead();
      toast.success(`Marked ${result.marked} as read`);
      await Promise.all([mutate("notifications"), mutate("notification-count")]);
    } catch {
      toast.error("Failed to mark all as read");
    } finally {
      setMarkingAll(false);
    }
  }

  async function handleDelete() {
    try {
      await deleteNotification(deleteId);
      toast.success("Notification deleted");
      setDeleteOpen(false);
      await Promise.all([mutate("notifications"), mutate("notification-count")]);
    } catch {
      toast.error("Failed to delete notification");
    }
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  if (notifications.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Notifications</h1>
        <EmptyState
          icon={
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10">
              <CheckCircle2 className="h-8 w-8 text-emerald-500" />
            </div>
          }
          title="All caught up!"
          description="You have no notifications right now."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Notifications</h1>
          {unreadCount > 0 && (
            <p className="text-sm text-muted-foreground mt-0.5">
              {unreadCount} unread notification{unreadCount !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        {unreadCount > 0 && (
          <Button variant="outline" size="sm" onClick={handleMarkAllRead} disabled={markingAll}>
            {markingAll ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5 mr-1.5" />
            )}
            {markingAll ? "Marking..." : "Mark all read"}
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {notifications.map((notification) => {
          const isUnread = !notification.is_read;
          return (
            <Card
              key={notification.id}
              className={`group transition-all duration-200 hover:shadow-md ${
                isUnread
                  ? "border-l-4 border-l-primary bg-primary/[0.03] dark:bg-primary/[0.06]"
                  : "border-l-4 border-l-transparent"
              }`}
            >
              <CardContent className="pt-3.5 pb-3.5">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 shrink-0">
                    <NotificationIcon title={notification.title} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className={`text-sm ${isUnread ? "font-semibold" : "font-medium"}`}>
                        {notification.title}
                      </p>
                      {isUnread && <div className="h-2 w-2 rounded-full bg-primary shrink-0" />}
                    </div>
                    <p className="text-sm text-muted-foreground">{notification.message}</p>
                    <p className="text-xs text-muted-foreground/60 mt-1 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatRelativeTime(notification.created_at)}
                    </p>
                  </div>
                  <div className="flex gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isUnread && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleMarkAsRead(notification.id)}
                        className="h-8 w-8 p-0"
                        aria-label="Mark as read"
                        title="Mark as read"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setDeleteId(notification.id);
                        setDeleteOpen(true);
                      }}
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                      aria-label="Delete notification"
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

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Notification"
        description="Are you sure you want to delete this notification?"
        onConfirm={handleDelete}
      />
    </div>
  );
}

export default function NotificationsPage() {
  const {
    data: notifications,
    error,
    mutate,
  } = useSWR("notifications", async () => {
    return listNotifications();
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!notifications)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <NotificationsContent notifications={notifications} />;
}
