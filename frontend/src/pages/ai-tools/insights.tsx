import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { InsightCard } from "@/components/members/insight-card";
import { InsightReport } from "@/components/members/insight-report-viewer";
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

  // Powers the Regenerate button inside the full-screen insight report.
  const insightRegen = useInsightStream(memberId, { onComplete: setInsight });

  useEffect(() => {
    if (!memberId) return;
    getLatestInsight(memberId)
      .then(setInsight)
      .catch(() => setInsight(null));
    getMember(memberId)
      .then(setMember)
      .catch(() => setMember(null));
  }, [memberId]);

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
