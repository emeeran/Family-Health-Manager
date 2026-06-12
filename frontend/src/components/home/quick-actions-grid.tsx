import { memo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { FileText, BellPlus, Sparkles, MessageSquare } from "lucide-react";

interface QuickActionsGridProps {
  members: { id: string; first_name: string; last_name: string; is_active: boolean }[];
}

export const QuickActionsGrid = memo(function QuickActionsGrid({ members }: QuickActionsGridProps) {
  const navigate = useNavigate();
  const firstActive = members.find((m) => m.is_active);

  const actions = [
    {
      label: "Add Record",
      icon: FileText,
      onClick: () => {
        if (firstActive) {
          navigate(`/people/${firstActive.id}/records/new`);
        } else {
          navigate("/people");
        }
      },
    },
    {
      label: "Add Reminder",
      icon: BellPlus,
      onClick: () => navigate("/people?tab=reminders"),
    },
    {
      label: "Smart Entry",
      icon: Sparkles,
      onClick: () => navigate("/ai-tools/smart-entry"),
    },
    {
      label: "Chat AI",
      icon: MessageSquare,
      onClick: () => navigate("/chat"),
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      {actions.map((action) => (
        <Button
          key={action.label}
          variant="outline"
          size="sm"
          className="h-9 justify-start gap-2 text-xs font-medium"
          onClick={action.onClick}
        >
          <action.icon className="h-3.5 w-3.5 text-muted-foreground" />
          {action.label}
        </Button>
      ))}
    </div>
  );
});
