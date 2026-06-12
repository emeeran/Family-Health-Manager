import { useState, useRef, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { streamRequest } from "@/lib/api-client";
import { generateMemberInsights } from "@/lib/api/members";
import { Brain, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import type { GeneratedInsight } from "@/lib/api/members";
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
  const [loading, setLoading] = useState(false);
  const [insight, setInsight] = useState<GeneratedInsight | null>(existingInsight);
  const [streamText, setStreamText] = useState("");
  const [streamStage, setStreamStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setStreamText("");
    setStreamStage("Starting...");
    try {
      let fullText = "";
      const { promise, cancel } = streamRequest(`/members/${memberId}/generate-insights/stream`, {
        onEvent: (event) => {
          const e = event as Record<string, unknown>;
          const stage = e.stage as string;
          if (stage === "context") {
            setStreamStage((e.message as string) || "Preparing...");
          } else if (stage === "provider") {
            setStreamStage(`Generating via ${e.provider}...`);
          } else if (stage === "token") {
            fullText += e.content as string;
            setStreamText(fullText);
          } else if (stage === "complete") {
            const result: GeneratedInsight = {
              id: e.insight_id as string,
              response: fullText,
              provider_used: e.provider as string,
              generated_at: new Date().toISOString(),
              verification: null,
            };
            setInsight(result);
            setStreamStage("");
            onInsightReady(result);
            generateMemberInsights(memberId)
              .then(() => {})
              .catch(() => {});
          } else if (stage === "error") {
            toast.error((e.message as string) || "Generation failed");
          }
        },
      });
      cancelRef.current = cancel;
      await promise;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to generate insights";
      setError(msg);
    } finally {
      setLoading(false);
      setStreamStage("");
      cancelRef.current = null;
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
          <div className="flex gap-2">
            {currentInsight && (
              <Button size="sm" variant="outline" onClick={onViewReport}>
                View Report
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleGenerate}
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
                onClick={() => cancelRef.current?.()}
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
            <Button size="sm" variant="outline" onClick={handleGenerate}>
              <Sparkles className="h-3.5 w-3.5 mr-1" />
              Retry
            </Button>
          </div>
        ) : currentInsight ? (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <p className="text-sm text-emerald-800">
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
