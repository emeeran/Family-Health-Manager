import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { MarkdownRenderer } from "@/components/shared/lazy-markdown";
import { MedicationReportView } from "@/components/members/reports/medication-report-view";
import type { MedicationReportData } from "@/lib/types/medication-report";
import { streamRequest } from "@/lib/api-client";
import { getLatestMedicationReport } from "@/lib/api/members";
import { FileText, Sparkles, Loader2, RefreshCw, Download } from "lucide-react";
import { toast } from "sonner";

interface MedicationReportDialogProps {
  memberId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Phase = "idle" | "loading-latest" | "streaming" | "done" | "error";

export function MedicationReportDialog({
  memberId,
  open,
  onOpenChange,
}: MedicationReportDialogProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [text, setText] = useState("");
  const [stage, setStage] = useState("");
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [hasReport, setHasReport] = useState(false);
  const [report, setReport] = useState<MedicationReportData | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  const loadLatest = useCallback(async () => {
    setPhase("loading-latest");
    try {
      const res = await getLatestMedicationReport(memberId);
      if (res.report) {
        setText(res.report.response || "");
        setReport(
          (res.report as { medication_report?: MedicationReportData }).medication_report ?? null
        );
        setGeneratedAt(res.report.generated_at);
        setHasReport(true);
        setPhase("done");
      } else {
        setText("");
        setHasReport(false);
        setPhase("idle");
      }
    } catch {
      setPhase("idle");
    }
  }, [memberId]);

  // Fast path: show the latest persisted report when the dialog opens.
  useEffect(() => {
    if (open) loadLatest();
    else {
      cancelRef.current?.();
      cancelRef.current = null;
      setStage("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset per open transition
  }, [open]);

  async function handleGenerate() {
    setPhase("streaming");
    setText("");
    setReport(null);
    setStage("Loading medications & safety data...");
    let full = "";
    try {
      const { promise, cancel } = streamRequest(`/members/${memberId}/medication-report/stream`, {
        onEvent: (event) => {
          const e = event as Record<string, unknown>;
          const s = e.stage as string;
          if (s === "context") setStage((e.message as string) || "Preparing...");
          else if (s === "provider") setStage(`Generating via ${e.provider}...`);
          else if (s === "token") {
            full += e.content as string;
            setText(full);
          } else if (s === "complete") {
            // Server postprocess ships the persisted payload in `report`.
            const payload =
              (e.report as
                | { response?: string; medication_report?: MedicationReportData }
                | undefined) ?? undefined;
            if (payload?.response) {
              full = payload.response;
              setText(full);
            }
            setReport(payload?.medication_report ?? null);
            setGeneratedAt((e.generated_at as string) ?? new Date().toISOString());
            setHasReport(true);
            setStage("");
          } else if (s === "error") {
            toast.error((e.message as string) || "Generation failed");
          }
        },
      });
      cancelRef.current = cancel;
      await promise;
      setPhase("done");
    } catch (err) {
      setPhase(hasReport ? "done" : "error");
      toast.error(err instanceof Error ? err.message : "Failed to generate report");
    } finally {
      setStage("");
      cancelRef.current = null;
    }
  }

  const streaming = phase === "streaming";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col gap-0 p-0">
        <DialogHeader className="p-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-violet-600" />
            Comprehensive Medication Report
          </DialogTitle>
          <DialogDescription className="text-xs">
            An AI overview of the current regimen — medicines, interactions, schedule, and safety
            alerts. For information only; not medical advice.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2 px-4 py-2 border-b bg-muted/30">
          <div className="text-[11px] text-muted-foreground">
            {generatedAt && !streaming && <>Generated {new Date(generatedAt).toLocaleString()}</>}
            {streaming && (
              <span className="flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                {stage || "Streaming..."}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {hasReport && text && !streaming && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() =>
                  download(
                    report ? JSON.stringify(report, null, 2) : text,
                    memberId,
                    report ? ".json" : ".md"
                  )
                }
              >
                <Download className="h-3 w-3 mr-1" /> Save
              </Button>
            )}
            <Button
              size="sm"
              className="h-7 text-xs"
              onClick={handleGenerate}
              disabled={streaming || phase === "loading-latest"}
            >
              {streaming ? (
                <>
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" /> Generating
                </>
              ) : hasReport ? (
                <>
                  <RefreshCw className="h-3 w-3 mr-1" /> Regenerate
                </>
              ) : (
                <>
                  <Sparkles className="h-3 w-3 mr-1" /> Generate
                </>
              )}
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="p-4 text-sm leading-relaxed">
            {phase === "loading-latest" && (
              <p className="text-muted-foreground">Loading latest report...</p>
            )}
            {phase === "idle" && (
              <p className="text-muted-foreground">
                No report yet. Click <strong>Generate</strong> to create a comprehensive medication
                report for this member.
              </p>
            )}
            {phase === "error" && (
              <p className="text-destructive">Failed to generate the report. Try again.</p>
            )}
            {report ? (
              <MedicationReportView report={report} />
            ) : (
              text && (
                <Suspense
                  fallback={<pre className="whitespace-pre-wrap text-xs font-sans">{text}</pre>}
                >
                  <MarkdownRenderer content={text} />
                </Suspense>
              )
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function download(content: string, memberId: string, ext: ".md" | ".json"): void {
  const blob = new Blob([content], {
    type: ext === ".json" ? "application/json" : "text/markdown",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `medication-report-${memberId}${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}
