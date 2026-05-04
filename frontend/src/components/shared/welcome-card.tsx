import { useState, useEffect } from "react";
import {
  X,
  CheckCircle2,
  Circle,
  Users,
  Stethoscope,
  FileText,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";

interface SetupStep {
  id: string;
  label: string;
  href: string;
  icon: React.ReactNode;
  check: boolean;
}

interface WelcomeCardProps {
  hasMembers: boolean;
  hasProviders: boolean;
  hasRecords: boolean;
  hasConversations: boolean;
}

const STORAGE_KEY = "health-manager-welcome-dismissed";

export function WelcomeCard({
  hasMembers,
  hasProviders,
  hasRecords,
  hasConversations,
}: WelcomeCardProps) {
  const [dismissed, setDismissed] = useState(true); // start true to avoid flash

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Only show if not dismissed AND setup is incomplete
    const isComplete = hasMembers && hasProviders && hasRecords;
    setDismissed(stored === "true" || isComplete);
  }, [hasMembers, hasProviders, hasRecords]);

  if (dismissed) return null;

  const steps: SetupStep[] = [
    {
      id: "member",
      label: "Add a family member",
      href: "/members/new",
      icon: <Users className="h-4 w-4" />,
      check: hasMembers,
    },
    {
      id: "provider",
      label: "Add a healthcare provider",
      href: "/providers/new",
      icon: <Stethoscope className="h-4 w-4" />,
      check: hasProviders,
    },
    {
      id: "record",
      label: "Add your first health record",
      href: "/records",
      icon: <FileText className="h-4 w-4" />,
      check: hasRecords,
    },
    {
      id: "chat",
      label: "Try Health AI assistant",
      href: "/conversations",
      icon: <MessageSquare className="h-4 w-4" />,
      check: hasConversations,
    },
  ];

  const completedCount = steps.filter((s) => s.check).length;

  return (
    <Card className="border-2 border-(--brand-accent)/30 bg-gradient-to-br from-(--brand-accent)/5 to-transparent">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-(--brand-accent)" />
            <h3 className="text-lg font-bold">Welcome to Health Keeper</h3>
          </div>
          <button
            onClick={() => {
              setDismissed(true);
              localStorage.setItem(STORAGE_KEY, "true");
            }}
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
            aria-label="Dismiss welcome card"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="text-sm text-muted-foreground mb-4">
          Get started by completing these steps. Your family's health journey begins here.
        </p>

        <div className="space-y-2">
          {steps.map((step) => (
            <div key={step.id} className="flex items-center gap-3">
              {step.check ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
              ) : (
                <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
              )}
              {step.check ? (
                <span className="text-sm text-muted-foreground line-through">{step.label}</span>
              ) : (
                <Link
                  to={step.href}
                  className="text-sm font-medium text-foreground hover:text-(--brand-accent) transition-colors flex items-center gap-1.5"
                >
                  {step.icon}
                  {step.label}
                </Link>
              )}
            </div>
          ))}
        </div>

        <p className="text-xs text-muted-foreground mt-4">
          {completedCount}/{steps.length} steps completed
        </p>
      </CardContent>
    </Card>
  );
}
