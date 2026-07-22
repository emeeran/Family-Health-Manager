import { useState, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { useInsightStream } from "@/lib/hooks/use-insight-stream";
import { StreamingPreview } from "@/components/members/reports/streaming-preview";
import type { GeneratedInsight } from "@/lib/api/members";
import { Brain, Sparkles, Loader2, CheckCircle2, Eye } from "lucide-react";
import { useVerificationPolling } from "@/lib/hooks/use-verification-polling";

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

  const { loading, streamText, streamStage, error, generate } = useInsightStream(memberId, {
    onComplete: (result) => {
      setInsight(result);
      onInsightReady(result);
    },
  });

  function handleCreate() {
    generate("comprehensive");
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
            <Button size="sm" onClick={onViewReport} disabled={!currentInsight} variant="outline">
              <Eye className="h-4 w-4 mr-1.5" />
              View
            </Button>
            <Button
              size="sm"
              onClick={handleCreate}
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
                  Create
                </>
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && streamText ? (
          <div className="p-3 rounded-lg bg-muted/30">
            <StreamingPreview text={streamText} stage={streamStage} />
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
            <Button size="sm" variant="outline" onClick={handleCreate}>
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
          <div className="flex items-start gap-3 rounded-lg border border-dashed border-(--brand-accent)/30 bg-gradient-to-br from-(--brand-accent)/5 to-transparent p-3.5">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-(--brand-accent)/10 ring-1 ring-(--brand-accent)/20">
              <Sparkles className="h-4 w-4 text-(--brand-accent)" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground/80">
                Generate an AI health report{memberFirstName ? ` for ${memberFirstName}` : ""}.
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Analyzes records, labs &amp; conditions into a structured assessment.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
});
