import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Plus, X, FileText, Users, Stethoscope, CalendarClock } from "lucide-react";
import { cn } from "@/lib/utils";
import { MemberFormSheet } from "@/components/members/member-form-sheet";
import { ProviderFormSheet } from "@/components/providers/provider-form-sheet";
import { ReminderFormSheet } from "@/components/reminders/reminder-form-sheet";
import { QuickAddRecordDialog } from "@/components/records/quick-add-record-dialog";
import useSWR from "swr";
import { listMembers } from "@/lib/api/members";

interface QuickAddOption {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  action: () => void;
}

export function UniversalQuickAdd() {
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [memberSheetOpen, setMemberSheetOpen] = useState(false);
  const [providerSheetOpen, setProviderSheetOpen] = useState(false);
  const [reminderSheetOpen, setReminderSheetOpen] = useState(false);
  const [recordDialogOpen, setRecordDialogOpen] = useState(false);

  const { data: members } = useSWR("quick-add-members", () => listMembers().catch(() => []));

  // Hide on mobile (bottom nav covers it) and on chat page
  const isChatPage = location.pathname === "/chat";
  if (isChatPage) return null;

  const options: QuickAddOption[] = [
    {
      label: "Add Record",
      icon: FileText,
      action: () => {
        setOpen(false);
        setRecordDialogOpen(true);
      },
    },
    {
      label: "Add Member",
      icon: Users,
      action: () => {
        setOpen(false);
        setMemberSheetOpen(true);
      },
    },
    {
      label: "Add Provider",
      icon: Stethoscope,
      action: () => {
        setOpen(false);
        setProviderSheetOpen(true);
      },
    },
    {
      label: "Add Reminder",
      icon: CalendarClock,
      action: () => {
        setOpen(false);
        setReminderSheetOpen(true);
      },
    },
  ];

  return (
    <>
      {/* FAB - desktop only */}
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className={cn(
            "hidden md:flex fixed bottom-6 right-6 z-40",
            "h-12 w-12 items-center justify-center rounded-full",
            "bg-primary text-primary-foreground shadow-lg",
            "hover:bg-primary/90 transition-all hover:scale-105"
          )}
          aria-label="Quick add"
        >
          <Plus className="h-5 w-5" />
        </button>
      ) : (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpen(false)} />
          {/* Options menu */}
          <div className="hidden md:flex fixed bottom-6 right-6 z-50 flex-col gap-2">
            {options.map((opt) => {
              const Icon = opt.icon;
              return (
                <button
                  key={opt.label}
                  onClick={opt.action}
                  className={cn(
                    "flex items-center gap-2 rounded-lg bg-card border px-4 py-2.5 shadow-md",
                    "text-sm font-medium hover:bg-muted/50 transition-colors"
                  )}
                >
                  <Icon className="h-4 w-4 text-primary" />
                  {opt.label}
                </button>
              );
            })}
            <button
              onClick={() => setOpen(false)}
              className={cn(
                "flex h-12 w-12 items-center justify-center rounded-full mx-auto",
                "bg-destructive text-destructive-foreground shadow-lg",
                "hover:bg-destructive/90 transition-all"
              )}
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </>
      )}

      {/* Sheet-based forms */}
      <MemberFormSheet open={memberSheetOpen} onOpenChange={setMemberSheetOpen} />
      <ProviderFormSheet open={providerSheetOpen} onOpenChange={setProviderSheetOpen} />
      <ReminderFormSheet open={reminderSheetOpen} onOpenChange={setReminderSheetOpen} />
      {members && members.length > 0 && (
        <QuickAddRecordDialog
          open={recordDialogOpen}
          onOpenChange={setRecordDialogOpen}
          members={members}
        />
      )}
    </>
  );
}
