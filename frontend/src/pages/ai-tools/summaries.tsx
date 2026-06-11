import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Eye, Loader2, Sparkles, RefreshCw } from "lucide-react";
import { listRecords, backfillSummaries, regenerateSummary } from "@/lib/api/records";
import { simpleMarkdown } from "@/lib/markdown";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";
import { toast } from "sonner";

export default function AiToolsSummariesPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [records, setRecords] = useState<HealthRecordResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [backfilling, setBackfilling] = useState(false);
  const [regenerating, setRegenerating] = useState<string | null>(null);

  useEffect(() => {
    if (!memberId) return;
    setLoading(true);
    listRecords(memberId)
      .then(setRecords)
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, [memberId]);

  async function handleBackfill() {
    setBackfilling(true);
    try {
      let totalUpdated = 0;
      let remaining = 1;
      while (remaining > 0) {
        const result = await backfillSummaries(memberId, 10);
        totalUpdated += result.updated_count;
        remaining = result.total_remaining;
        if (result.updated_count === 0 && remaining > 0) break;
      }
      toast.success(`Generated ${totalUpdated} summaries`);
      // Refresh records
      const updated = await listRecords(memberId);
      setRecords(updated);
    } catch {
      toast.error("Failed to generate summaries");
    } finally {
      setBackfilling(false);
    }
  }

  async function handleRegenerate(recordId: string) {
    setRegenerating(recordId);
    try {
      const result = await regenerateSummary(memberId, recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? result : r)));
      toast.success("Summary regenerated");
    } catch {
      toast.error("Failed to regenerate summary");
    } finally {
      setRegenerating(null);
    }
  }

  const withSummary = records.filter((r) => r.summary);
  const withoutSummary = records.filter((r) => !r.summary);

  return (
    <AiToolsSubPage title="Consultation Summaries">
      <div className="space-y-4">
        {/* Stats + backfill */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-sm">
            <span>{records.length} records</span>
            <Badge variant="secondary" className="bg-emerald-100 text-emerald-700">
              {withSummary.length} with summary
            </Badge>
            {withoutSummary.length > 0 && (
              <Badge variant="secondary" className="bg-amber-100 text-amber-700">
                {withoutSummary.length} missing
              </Badge>
            )}
          </div>
          {withoutSummary.length > 0 && (
            <Button size="sm" onClick={handleBackfill} disabled={backfilling}>
              {backfilling ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5 mr-1" />
              )}
              {backfilling ? "Generating..." : "Generate Missing"}
            </Button>
          )}
        </div>

        {/* Record summaries */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : withSummary.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            No summaries yet. Click "Generate Missing" to create them.
          </div>
        ) : (
          <div className="space-y-3">
            {withSummary.map((record) => (
              <details key={record.id} className="rounded-lg border bg-card overflow-hidden group">
                <summary className="px-4 py-3 cursor-pointer flex items-center gap-3 hover:bg-muted/30 transition-colors">
                  <Eye className="h-4 w-4 text-emerald-600 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {record.diagnosis ||
                          RECORD_TYPE_LABELS[record.record_type as RecordType] ||
                          record.record_type}
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {RECORD_TYPE_LABELS[record.record_type as RecordType] || record.record_type}
                      </Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(record.record_date)}
                      {record.provider_name && ` · ${record.provider_name}`}
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRegenerate(record.id);
                    }}
                    disabled={regenerating === record.id}
                  >
                    {regenerating === record.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3 w-3" />
                    )}
                  </Button>
                </summary>
                <div className="px-4 pb-3 border-t">
                  <div
                    className="text-xs text-muted-foreground leading-relaxed prose prose-sm max-w-none prose-table:text-[11px] prose-th:px-1.5 prose-th:py-0.5 prose-td:px-1.5 prose-td:py-0.5 prose-th:bg-muted/50"
                    dangerouslySetInnerHTML={{ __html: simpleMarkdown(record.summary || "") }}
                  />
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </AiToolsSubPage>
  );
}
