import { cn } from "@/lib/utils";
import { CheckCircle2 } from "lucide-react";

export interface StepperStep {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  optional?: boolean;
}

interface StepperProps {
  steps: StepperStep[];
  currentStep: number;
  completedSteps?: number[];
  onStepClick?: (step: number) => void;
  size?: "sm" | "default";
  className?: string;
}

export function Stepper({
  steps,
  currentStep,
  completedSteps = [],
  onStepClick,
  size = "default",
  className,
}: StepperProps) {
  const isCompleted = (i: number) => completedSteps.includes(i) || i < currentStep;

  return (
    <div className={cn("flex items-center justify-center gap-2", className)}>
      {steps.map((s, i) => {
        const Icon = s.icon;
        const isActive = i === currentStep;
        const done = isCompleted(i);
        const clickable = onStepClick && (done || Math.abs(i - currentStep) === 1);
        const circleSize = size === "sm" ? "h-7 w-7" : "h-9 w-9";
        const iconSize = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
        const lineSize = size === "sm" ? "w-6" : "w-8";

        return (
          <div key={i} className="flex items-center gap-2">
            {i > 0 && (
              <div
                className={cn(
                  "h-px transition-colors",
                  lineSize,
                  done ? "bg-primary" : "bg-border"
                )}
              />
            )}
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onStepClick(i)}
              className={cn(
                "flex items-center justify-center rounded-full transition-all",
                circleSize,
                isActive
                  ? "bg-primary text-primary-foreground shadow-md"
                  : done
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground",
                clickable && "cursor-pointer hover:opacity-80"
              )}
              aria-label={`Step ${i + 1}: ${s.label}${done ? " (completed)" : ""}${isActive ? " (current)" : ""}`}
              aria-current={isActive ? "step" : undefined}
            >
              {done && !isActive ? (
                <CheckCircle2 className={iconSize} />
              ) : Icon ? (
                <Icon className={iconSize} />
              ) : (
                <span className={cn("font-semibold", size === "sm" ? "text-xs" : "text-sm")}>
                  {i + 1}
                </span>
              )}
            </button>
            {steps.length <= 5 && (
              <span
                className={cn(
                  "hidden sm:inline text-xs font-medium",
                  isActive ? "text-foreground" : "text-muted-foreground",
                  s.optional && "text-muted-foreground/60"
                )}
              >
                {s.label}
                {s.optional && (
                  <span className="ml-1 text-[10px] text-muted-foreground/50 lowercase">
                    optional
                  </span>
                )}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
