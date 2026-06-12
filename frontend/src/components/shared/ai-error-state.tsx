import { Button } from "@/components/ui/button";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface AiErrorStateProps {
  /** Error message to display */
  message: string;
  /** Retry handler — if provided, shows a retry button */
  onRetry?: () => void;
  /** Optional secondary action label */
  secondaryLabel?: string;
  /** Optional secondary action handler */
  onSecondary?: () => void;
  /** Compact mode — smaller padding, for inline use */
  compact?: boolean;
}

/**
 * Reusable error state for AI tool components.
 * Shows the error message with optional retry/secondary actions.
 */
export function AiErrorState({
  message,
  onRetry,
  secondaryLabel,
  onSecondary,
  compact = false,
}: AiErrorStateProps) {
  return (
    <div
      className={
        compact
          ? "flex items-center gap-2 text-xs text-destructive"
          : "p-3 rounded-lg bg-destructive/10 border border-destructive/20 space-y-2"
      }
    >
      <div className={compact ? "flex items-center gap-1.5" : "flex items-start gap-2"}>
        <AlertTriangle className={compact ? "h-3 w-3 shrink-0" : "h-4 w-4 shrink-0 mt-0.5"} />
        <p className={compact ? "font-medium" : "text-sm font-medium"}>{message}</p>
      </div>
      {(onRetry || onSecondary) && (
        <div className={compact ? "flex items-center gap-1.5 ml-4" : "flex items-center gap-2"}>
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry} className="h-7 text-xs gap-1">
              <RefreshCw className="h-3 w-3" />
              Retry
            </Button>
          )}
          {onSecondary && (
            <Button size="sm" variant="ghost" onClick={onSecondary} className="h-7 text-xs">
              {secondaryLabel || "Try different parameters"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
