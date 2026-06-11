import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { DrugInteractionReport } from "@/components/members/drug-interaction-report";
import { getMemberDetail } from "@/lib/api/members";

export default function AiToolsDrugInteractionsPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [medicationCount, setMedicationCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!memberId) return;
    getMemberDetail(memberId)
      .then((data) => {
        setMedicationCount(data.active_medications_count ?? 0);
      })
      .catch(() => setMedicationCount(0))
      .finally(() => setLoading(false));
  }, [memberId]);

  return (
    <AiToolsSubPage title="Drug Interactions">
      <div className="max-w-2xl">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : (
          <DrugInteractionReport memberId={memberId} medicationCount={medicationCount} />
        )}
      </div>
    </AiToolsSubPage>
  );
}
