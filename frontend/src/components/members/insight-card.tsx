import { useState, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { useInsightStream } from "@/lib/hooks/use-insight-stream";
import type { GeneratedInsight, InsightMode } from "@/lib/api/members";
import { Brain, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { useVerificationPolling } from "@/lib/hooks/use-verification-polling";
import { cn } from "@/lib/utils";

function ModeToggle({
  mode,
  onChange,
  disabled,
}: {
  mode: InsightMode;
  onChange: (m: InsightMode) => void;
  disabled?: boolean;
}) {
  const options: { value: InsightMode; label: string; title: string }[] = [
    { value: "comprehensive", label: "Comprehensive", title: "Full detailed report (slower)" },
    { value: "brief", label: "Concise", title: "Shorter report, ~2× faster" },
  ];
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-md border border-border bg-muted/40 p-0.5",
        disabled && "pointer-events-none opacity-50"
      )}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
            mode === o.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export interface InsightCardProps {
  memberId: string;
  memberFirstName: string;
  onInsightReady: (insight: GeneratedInsight) => void;
  onViewReport: () => void;
  existingInsight: GeneratedInsight | null;
}

export const InsightCard = memo(function InsightCard({
  memberId,
  memberFirstName,
  onInsightReady,
  onViewReport,
  existingInsight,
}: InsightCardProps) {
  const [insight, setInsight] = useState<GeneratedInsight | null>(existingInsight);
  const [mode, setMode] = useState<InsightMode>(() => {
    try {
      return (localStorage.getItem("insightMode") as InsightMode) || "comprehensive";
    } catch {
      return "comprehensive";
    }
  });

  const { loading, streamText, streamStage, error, generate, cancel } = useInsightStream(memberId, {
    onComplete: (result) => {
      setInsight(result);
      onInsightReady(result);
    },
  });

  function chooseMode(m: InsightMode) {
    setMode(m);
    try {
      localStorage.setItem("insightMode", m);
    } catch {
      /* localStorage unavailable — keep session-only state */
    }
  }

  const currentInsight = insight || existingInsight;
  const verification = useVerificationPolling(memberId, currentInsight);

  return (
    <Card className="overflow-hidden">
      <div className="h-1.5 bg-gradient-to-r from-(--brand-accent) to-(--brand-primary)" />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Brain className="h-5 w-5 text-(--brand-accent)" />
            AI Health Insights
          </CardTitle>
          <div className="flex items-center gap-2">
            <ModeToggle mode={mode} onChange={chooseMode} disabled={loading} />
            {currentInsight && (
              <Button size="sm" variant="outline" onClick={onViewReport}>
                View Report
              </Button>
            )}
            <Button
              size="sm"
              onClick={() => generate(mode)}
              disabled={loading}
              className="bg-gradient-to-r from-(--brand-accent) to-orange-600 text-white hover:from-orange-700 hover:to-orange-700"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-1.5" />
                  {currentInsight ? "Regenerate" : "Generate"}
                </>
              )}
            </Button>
            {loading && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs text-muted-foreground"
                onClick={cancel}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && streamText ? (
          <div className="p-3 rounded-lg bg-muted/30">
            {streamStage && (
              <p className="text-xs text-(--brand-accent) font-medium mb-2">{streamStage}</p>
            )}
            <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
              {streamText}
              <span className="inline-block w-1.5 h-4 bg-(--brand-accent) animate-pulse ml-0.5 align-text-bottom" />
            </p>
          </div>
        ) : loading ? (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
            <Loader2 className="h-5 w-5 animate-spin text-(--brand-accent)" />
            <p className="text-sm text-foreground/70 font-medium">
              {streamStage || "Analyzing records..."}
            </p>
          </div>
        ) : error ? (
          <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 space-y-2">
            <p className="text-sm text-destructive font-medium">{error}</p>
            <Button size="sm" variant="outline" onClick={() => generate(mode)}>
              <Sparkles className="h-3.5 w-3.5 mr-1" />
              Retry
            </Button>
          </div>
        ) : currentInsight ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <p className="text-sm text-emerald-700 dark:text-emerald-400">
              Report generated{" "}
              {new Date(currentInsight.generated_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}{" "}
              via <span className="font-bold">{currentInsight.provider_used}</span>
            </p>
            <VerificationBadge verification={verification} />
          </div>
        ) : (
          <p className="text-sm text-foreground/60">
            Click Generate to create an AI health report for {memberFirstName}.
          </p>
        )}
      </CardContent>
    </Card>
  );
});
