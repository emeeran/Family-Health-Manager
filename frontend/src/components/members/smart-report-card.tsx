import { useState, useRef, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { streamRequest } from "@/lib/api-client";
import { ClipboardList, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import type { GeneratedInsight } from "@/lib/api/members";
import { useVerificationPolling } from "@/lib/hooks/use-verification-polling";

export interface SmartReportCardProps {
  memberId: string;
  memberFirstName: string;
  existingReport: GeneratedInsight | null;
  onReportReady: (report: GeneratedInsight) => void;
  onViewReport: () => void;
}

export const SmartReportCard = memo(function SmartReportCard({
  memberId,
  memberFirstName,
  existingReport,
  onReportReady,
  onViewReport,
}: SmartReportCardProps) {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<GeneratedInsight | null>(existingReport);
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
      const { promise, cancel } = streamRequest(`/members/${memberId}/smart-report/stream`, {
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
            setReport(result);
            setStreamStage("");
            onReportReady(result);
          } else if (stage === "error") {
            toast.error((e.message as string) || "Generation failed");
          }
        },
      });
      cancelRef.current = cancel;
      await promise;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to generate Smart Report";
      setError(msg);
    } finally {
      setLoading(false);
      setStreamStage("");
      cancelRef.current = null;
    }
  }

  const currentReport = report || existingReport;
  const verification = useVerificationPolling(memberId, currentReport);

  return (
    <Card className="overflow-hidden">
      <div className="h-1.5 bg-gradient-to-r from-purple-500 to-indigo-600" />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-purple-600" />
            Smart Report
          </CardTitle>
          <div className="flex gap-2">
            {currentReport && (
              <Button size="sm" variant="outline" onClick={onViewReport}>
                View Report
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={loading}
              className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white hover:from-purple-700 hover:to-indigo-700"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-1.5" />
                  {currentReport ? "Regenerate" : "Generate"}
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
              <p className="text-xs text-purple-600 font-medium mb-2">{streamStage}</p>
            )}
            <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
              {streamText}
              <span className="inline-block w-1.5 h-4 bg-purple-600 animate-pulse ml-0.5 align-text-bottom" />
            </p>
          </div>
        ) : loading ? (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
            <Loader2 className="h-5 w-5 animate-spin text-purple-600" />
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
        ) : currentReport ? (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <p className="text-sm text-emerald-800">
              Report generated{" "}
              {new Date(currentReport.generated_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}{" "}
              via <span className="font-bold">{currentReport.provider_used}</span>
            </p>
            <VerificationBadge verification={verification} />
          </div>
        ) : (
          <p className="text-sm text-foreground/60">
            Click Generate to create a comprehensive Smart Report for {memberFirstName}.
          </p>
        )}
      </CardContent>
    </Card>
  );
});
