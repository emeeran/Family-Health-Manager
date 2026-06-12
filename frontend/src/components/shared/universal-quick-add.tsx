import { useState, useRef, useCallback, useEffect } from "react";
import { useLocation } from "react-router-dom";
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
  colorDot: string;
}

/** Default position: 24px from bottom-right corner */
const DEFAULT_POS = { x: 24, y: 24 };
const FAB_SIZE = 48; // h-12 w-12 in px

export function UniversalQuickAdd() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [memberSheetOpen, setMemberSheetOpen] = useState(false);
  const [providerSheetOpen, setProviderSheetOpen] = useState(false);
  const [reminderSheetOpen, setReminderSheetOpen] = useState(false);
  const [recordDialogOpen, setRecordDialogOpen] = useState(false);

  // ── Draggable state ──
  const [pos, setPos] = useState(() => {
    try {
      const saved = localStorage.getItem("fab-position");
      return saved ? JSON.parse(saved) : DEFAULT_POS;
    } catch {
      return DEFAULT_POS;
    }
  });
  const dragging = useRef(false);
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 });
  const hasMoved = useRef(false);

  const { data: members } = useSWR("quick-add-members", () => listMembers().catch(() => []));

  // Hide on mobile (bottom nav covers it) and on chat page
  const isChatPage = location.pathname === "/chat";
  if (isChatPage) return null;

  // ── Drag handlers ──
  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      // Only react to primary button / touch
      if (e.button !== 0) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      dragging.current = true;
      hasMoved.current = false;
      dragStart.current = {
        mx: e.clientX,
        my: e.clientY,
        px: pos.x,
        py: pos.y,
      };
    },
    [pos]
  );

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLButtonElement>) => {
    if (!dragging.current) return;
    const dx = e.clientX - dragStart.current.mx;
    const dy = e.clientY - dragStart.current.my;

    // Require a small threshold before treating as a drag (vs click)
    if (!hasMoved.current && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    hasMoved.current = true;

    const newX = dragStart.current.px - dx;
    const newY = dragStart.current.py - dy;

    // Clamp to viewport
    const clampedX = Math.max(0, Math.min(newX, window.innerWidth - FAB_SIZE));
    const clampedY = Math.max(0, Math.min(newY, window.innerHeight - FAB_SIZE));

    setPos({ x: clampedX, y: clampedY });
  }, []);

  const onPointerUp = useCallback(() => {
    dragging.current = false;
    if (hasMoved.current) {
      // Persist position
      try {
        localStorage.setItem("fab-position", JSON.stringify(pos));
      } catch {
        // ignore quota errors
      }
    }
  }, [pos]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      dragging.current = false;
    };
  }, []);

  const options: QuickAddOption[] = [
    {
      label: "Add Record",
      icon: FileText,
      action: () => {
        setOpen(false);
        setRecordDialogOpen(true);
      },
      colorDot: "bg-blue-500",
    },
    {
      label: "Add Member",
      icon: Users,
      action: () => {
        setOpen(false);
        setMemberSheetOpen(true);
      },
      colorDot: "bg-emerald-500",
    },
    {
      label: "Add Provider",
      icon: Stethoscope,
      action: () => {
        setOpen(false);
        setProviderSheetOpen(true);
      },
      colorDot: "bg-violet-500",
    },
    {
      label: "Add Reminder",
      icon: CalendarClock,
      action: () => {
        setOpen(false);
        setReminderSheetOpen(true);
      },
      colorDot: "bg-amber-500",
    },
  ];

  // Compute whether the FAB is closer to the left or right edge
  // to flip the options menu accordingly
  const isOnLeft = pos.x < window.innerWidth / 2;

  return (
    <>
      {/* FAB - desktop only */}
      {!open ? (
        <button
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onClick={() => {
            // Only toggle menu if we didn't drag
            if (!hasMoved.current) setOpen(true);
          }}
          className={cn(
            "hidden md:flex fixed z-40",
            "h-12 w-12 items-center justify-center rounded-full",
            "bg-gradient-to-br from-[var(--brand-accent)] to-[var(--brand-primary)] text-white",
            "shadow-lg shadow-[var(--brand-accent)]/20",
            "hover:scale-105 transition-shadow animate-float touch-none select-none",
            "cursor-grab active:cursor-grabbing"
          )}
          style={{
            right: pos.x,
            bottom: pos.y,
          }}
          aria-label="Quick add (drag to reposition)"
        >
          <Plus className="h-5 w-5 pointer-events-none" />
        </button>
      ) : (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpen(false)} />
          {/* Options menu */}
          <div
            className={cn(
              "hidden md:flex fixed z-50 flex-col gap-2",
              isOnLeft ? "items-start" : "items-end"
            )}
            style={{
              right: isOnLeft ? undefined : pos.x,
              left: isOnLeft ? pos.x : undefined,
              bottom: pos.y,
            }}
          >
            {options.map((opt, index) => {
              const Icon = opt.icon;
              return (
                <button
                  key={opt.label}
                  onClick={opt.action}
                  className={cn(
                    "animate-fade-in-up flex items-center gap-2.5 rounded-lg bg-card border px-4 py-2.5 shadow-md",
                    "text-sm font-medium hover:bg-muted/50 transition-colors"
                  )}
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  <div className={`h-2 w-2 rounded-full ${opt.colorDot}`} />
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
