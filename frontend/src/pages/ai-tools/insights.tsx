import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { InsightCard } from "@/components/members/insight-card";
import { InsightReport } from "@/components/members/insight-report-viewer";
import { ErrorState } from "@/components/shared/error-state";
import { getLatestInsight } from "@/lib/api/members";
import { getMember } from "@/lib/api/members";
import { useInsightStream } from "@/lib/hooks/use-insight-stream";
import type { GeneratedInsight } from "@/lib/api/members";
import type { FamilyMemberResponse } from "@/lib/types/member";

export default function AiToolsInsightsPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [insight, setInsight] = useState<GeneratedInsight | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [member, setMember] = useState<FamilyMemberResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Powers the Regenerate button inside the full-screen insight report.
  const insightRegen = useInsightStream(memberId, { onComplete: setInsight });

  const loadData = useCallback(() => {
    if (!memberId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([getLatestInsight(memberId), getMember(memberId)])
      .then(([ins, mem]) => {
        setInsight(ins);
        setMember(mem);
      })
      .catch(() => {
        setError("Could not load — check your connection and retry");
        setInsight(null);
        setMember(null);
      })
      .finally(() => setLoading(false));
  }, [memberId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <AiToolsSubPage title="Health Insights">
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      </AiToolsSubPage>
    );
  }

  if (error) {
    return (
      <AiToolsSubPage title="Health Insights">
        <ErrorState message={error} onRetry={loadData} />
      </AiToolsSubPage>
    );
  }

  if (showReport && insight) {
    return (
      <AiToolsSubPage title="Health Insights">
        <InsightReport
          response={insight.response}
          provider={insight.provider_used}
          generatedAt={insight.generated_at}
          verification={insight.verification}
          sections={insight.sections}
          memberName={member ? `${member.first_name} ${member.last_name}` : ""}
          memberDob={member?.date_of_birth || ""}
          memberGender={member?.gender || ""}
          memberId={memberId}
          onBack={() => setShowReport(false)}
          onRegenerate={() => insightRegen.generate()}
          regenerating={insightRegen.loading}
          regenerateStage={insightRegen.streamStage}
          regenerateText={insightRegen.streamText}
          onCancelRegenerate={insightRegen.cancel}
        />
      </AiToolsSubPage>
    );
  }

  return (
    <AiToolsSubPage title="Health Insights">
      <div className="max-w-2xl">
        <InsightCard
          memberId={memberId}
          memberFirstName=""
          existingInsight={insight}
          onInsightReady={setInsight}
          onViewReport={() => setShowReport(true)}
        />
      </div>
    </AiToolsSubPage>
  );
}
