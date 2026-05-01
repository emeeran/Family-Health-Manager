import { CheckCircle2, AlertTriangle, HelpCircle, Loader2, XCircle, Shield } from "lucide-react";
import type { VerificationResult } from "@/lib/types/message";
import { cn } from "@/lib/utils";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";

export function VerificationBadge({
  verification,
}: {
  verification: VerificationResult | null | undefined;
}) {
  if (!verification || verification.status === "failed") return null;

  const { status, summary, warnings, claims_checked, verifier_provider } = verification;

  const config = {
    verified: {
      icon: CheckCircle2,
      color: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-500/10",
      label: "Verified",
      titleColor: "text-emerald-700",
    },
    warnings: {
      icon: AlertTriangle,
      color: "text-amber-600 dark:text-amber-400",
      bg: "bg-amber-500/10",
      label: "Warnings",
      titleColor: "text-amber-700",
    },
    unverifiable: {
      icon: HelpCircle,
      color: "text-muted-foreground",
      bg: "bg-muted/50",
      label: "Unverifiable",
      titleColor: "text-muted-foreground",
    },
    pending: {
      icon: Loader2,
      color: "text-muted-foreground",
      bg: "bg-muted/50",
      label: "Checking...",
      titleColor: "text-muted-foreground",
    },
  }[status] ?? {
    icon: XCircle,
    color: "text-muted-foreground",
    bg: "bg-muted/50",
    label: status,
    titleColor: "text-muted-foreground",
  };

  const Icon = config.icon;

  // Compact badge
  const badge = (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium cursor-default",
        config.bg,
        config.color,
        status === "pending" && "animate-pulse"
      )}
    >
      <Icon className={cn("h-2.5 w-2.5", status === "pending" && "animate-spin")} />
      {config.label}
    </span>
  );

  // Pending state — no popover, just animated badge
  if (status === "pending") return badge;

  return (
    <Popover>
      <PopoverTrigger className="outline-none">{badge}</PopoverTrigger>
      <PopoverContent side="top" align="end" className="w-80 p-0">
        <PopoverHeader className="p-3 pb-2 border-b">
          <div className="flex items-center gap-2">
            <Shield className={cn("h-4 w-4", config.color)} />
            <PopoverTitle className={cn("text-sm", config.titleColor)}>
              {status === "verified" && "Fact-Checked & Verified"}
              {status === "warnings" && "Verification Warnings Found"}
              {status === "unverifiable" && "Could Not Verify"}
            </PopoverTitle>
          </div>
          <PopoverDescription className="text-xs mt-1">
            {summary || "Cross-checked against medical records."}
          </PopoverDescription>
        </PopoverHeader>

        <div className="p-3 space-y-2">
          {/* Meta info */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{claims_checked} claims checked</span>
            {verifier_provider && <span>via {verifier_provider}</span>}
          </div>

          {/* Warnings */}
          {warnings && warnings.length > 0 && (
            <div className="space-y-1.5">
              {warnings.map((w, i) => (
                <div
                  key={i}
                  className={cn(
                    "rounded-md border p-2 text-xs",
                    w.severity === "high"
                      ? "border-red-200 bg-red-50"
                      : w.severity === "medium"
                        ? "border-amber-200 bg-amber-50"
                        : "border-muted bg-muted/30"
                  )}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className={cn(
                        "font-semibold capitalize",
                        w.severity === "high"
                          ? "text-red-600"
                          : w.severity === "medium"
                            ? "text-amber-600"
                            : "text-muted-foreground"
                      )}
                    >
                      {w.type.replace(/_/g, " ")}
                    </span>
                    <span
                      className={cn(
                        "text-[9px] px-1 py-0.5 rounded font-medium",
                        w.severity === "high"
                          ? "bg-red-100 text-red-700"
                          : w.severity === "medium"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-muted text-muted-foreground"
                      )}
                    >
                      {w.severity}
                    </span>
                  </div>
                  {w.claim && <p className="text-muted-foreground line-through">{w.claim}</p>}
                  <p>{w.correction}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
