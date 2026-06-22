import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import {
  RecordsEmptyIllustration,
  MembersEmptyIllustration,
  ProvidersEmptyIllustration,
  RemindersEmptyIllustration,
  TimelineEmptyIllustration,
} from "@/components/shared/empty-state-illustrations";
import { Search, AlertTriangle } from "lucide-react";

type EmptyStateVariant = "no-data" | "filtered" | "error";
type EmptyStateContext =
  | "records"
  | "members"
  | "providers"
  | "reminders"
  | "timeline"
  | "provider-assignments";

interface ContextualEmptyStateProps {
  variant: EmptyStateVariant;
  context: EmptyStateContext;
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

/* ── Illustration map ── */
const illustrations: Record<EmptyStateContext, React.ComponentType<{ className?: string }>> = {
  records: RecordsEmptyIllustration,
  members: MembersEmptyIllustration,
  providers: ProvidersEmptyIllustration,
  reminders: RemindersEmptyIllustration,
  timeline: TimelineEmptyIllustration,
  "provider-assignments": ProvidersEmptyIllustration,
};

/* ── Presets per variant × context ── */
type Preset = { title: string; description: string; action?: React.ReactNode };
const presets: Record<EmptyStateVariant, Partial<Record<EmptyStateContext, Preset>>> = {
  "no-data": {
    records: {
      title: "No records yet",
      description: "Start by adding a health record for your family members.",
      action: (
        <Link to="/people">
          <Button size="sm">Add First Record</Button>
        </Link>
      ),
    },
    members: {
      title: "No family members",
      description: "Add your first family member to begin tracking health records.",
      action: (
        <Link to="/people/new">
          <Button size="sm">Add Member</Button>
        </Link>
      ),
    },
    providers: {
      title: "No healthcare providers",
      description: "Add a provider to associate with health records.",
      action: (
        <Link to="/providers/new">
          <Button size="sm">Add Provider</Button>
        </Link>
      ),
    },
    reminders: {
      title: "No reminders",
      description: "Set up medication or appointment reminders for your family.",
      action: (
        <Link to="/people?tab=reminders">
          <Button size="sm">Add Reminder</Button>
        </Link>
      ),
    },
    timeline: {
      title: "No timeline entries",
      description: "Health records will appear here as you add them.",
    },
    "provider-assignments": {
      title: "No providers assigned",
      description: "Link a provider to this member's records.",
      action: (
        <Link to="/providers/new">
          <Button size="sm">Assign Provider</Button>
        </Link>
      ),
    },
  },
  filtered: {
    records: {
      title: "No matching records",
      description: "Try adjusting your filters or date range.",
    },
    members: {
      title: "No matching members",
      description: "Try adjusting your search.",
    },
    providers: {
      title: "No matching providers",
      description: "Try adjusting your search.",
    },
    reminders: {
      title: "No matching reminders",
      description: "Try adjusting your status filter.",
    },
    timeline: {
      title: "No entries in this range",
      description: "Try selecting a different time period.",
    },
    "provider-assignments": {
      title: "No matching providers",
      description: "Try adjusting your search.",
    },
  },
  error: {
    records: {
      title: "Failed to load records",
      description: "Something went wrong. Please try again.",
    },
    members: {
      title: "Failed to load members",
      description: "Something went wrong. Please try again.",
    },
    providers: {
      title: "Failed to load providers",
      description: "Something went wrong. Please try again.",
    },
    reminders: {
      title: "Failed to load reminders",
      description: "Something went wrong. Please try again.",
    },
    timeline: {
      title: "Failed to load timeline",
      description: "Something went wrong. Please try again.",
    },
    "provider-assignments": {
      title: "Failed to load",
      description: "Something went wrong. Please try again.",
    },
  },
};

export function ContextualEmptyState({
  variant,
  context,
  title: titleOverride,
  description: descriptionOverride,
  action: actionOverride,
  className,
}: ContextualEmptyStateProps) {
  const preset = presets[variant]?.[context];
  const title = titleOverride ?? preset?.title ?? "Nothing here";
  const description = descriptionOverride ?? preset?.description;
  const action = actionOverride !== undefined ? actionOverride : preset?.action;

  // For "filtered" variant, use compact with icon instead of illustration
  if (variant === "filtered") {
    return (
      <EmptyState
        variant="compact"
        icon={<Search className="h-8 w-8 text-muted-foreground/40" />}
        title={title}
        description={description}
        action={action}
        className={className}
      />
    );
  }

  // For "error" variant, use compact with alert icon
  if (variant === "error") {
    return (
      <EmptyState
        variant="compact"
        icon={<AlertTriangle className="h-8 w-8 text-destructive/40" />}
        title={title}
        description={description}
        action={action}
        className={className}
      />
    );
  }

  // "no-data" — full illustrated variant
  const Illustration = illustrations[context];
  return (
    <EmptyState
      variant="illustrated"
      illustration={<Illustration />}
      title={title}
      description={description}
      action={action}
      className={className}
    />
  );
}
