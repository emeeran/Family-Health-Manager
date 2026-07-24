import { useState, useRef, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { streamRequest } from "@/lib/api-client";
import { ClipboardList, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import type { GeneratedInsight } from "@/lib/api/members";
import type { SmartReportData } from "@/lib/types/smart-report";
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
  const [streamStage, setStreamStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
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
          } else if (stage === "complete") {
            // Backend post-processes the final frame with the parsed report
            // (race-free — no second round-trip). `fullText` is kept only as a
            // defensive fallback when the payload isn't post-processed.
            const reportObj =
              typeof e.report === "object" && e.report !== null
                ? (e.report as SmartReportData)
                : null;
            const raw = (e.raw_response as string) ?? fullText;
            const result: GeneratedInsight = {
              id: (e.insight_id as string) ?? (e.id as string),
              response: raw,
              raw_response: raw,
              report: reportObj,
              provider_used: e.provider as string,
              generated_at: (e.generated_at as string) ?? new Date().toISOString(),
              verification:
                (e.verification as GeneratedInsight["verification"] | undefined) ?? null,
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
        {loading ? (
          <div className="flex items-center gap-3 rounded-lg bg-muted/30 p-3">
            <Loader2 className="h-5 w-5 animate-spin text-purple-600" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground/80">
                {streamStage || "Analyzing records..."}
              </p>
              <p className="text-[11px] text-muted-foreground">Compiling structured report…</p>
            </div>
          </div>
        ) : error ? (
          <div className="space-y-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3">
            <p className="text-sm font-medium text-destructive">{error}</p>
            <Button size="sm" variant="outline" onClick={handleGenerate}>
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              Retry
            </Button>
          </div>
        ) : currentReport ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <p className="text-sm text-emerald-700 dark:text-emerald-400">
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
