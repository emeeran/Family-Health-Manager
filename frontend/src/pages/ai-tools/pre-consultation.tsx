import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { PreConsultationCard } from "@/components/members/pre-consultation-card";
import { PreConsultationNoteViewer } from "@/components/members/insight-report-viewer";
import { ErrorState } from "@/components/shared/error-state";
import { getLatestPreConsultationNote, getMember } from "@/lib/api/members";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { GeneratedInsight } from "@/lib/api/members";

export default function AiToolsPreConsultPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [note, setNote] = useState<GeneratedInsight | null>(null);
  const [showNote, setShowNote] = useState(false);
  const [member, setMember] = useState<FamilyMemberResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(() => {
    if (!memberId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([getLatestPreConsultationNote(memberId), getMember(memberId)])
      .then(([res, mem]) => {
        setNote(res.note);
        setMember(mem);
      })
      .catch(() => {
        setError("Could not load — check your connection and retry");
        setNote(null);
        setMember(null);
      })
      .finally(() => setLoading(false));
  }, [memberId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <AiToolsSubPage title="Pre-consultation Notes">
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      </AiToolsSubPage>
    );
  }

  if (error) {
    return (
      <AiToolsSubPage title="Pre-consultation Notes">
        <ErrorState message={error} onRetry={loadData} />
      </AiToolsSubPage>
    );
  }

  if (showNote && note) {
    return (
      <AiToolsSubPage title="Pre-consultation Notes">
        <PreConsultationNoteViewer
          response={note.response}
          provider={note.provider_used}
          generatedAt={note.generated_at}
          memberName={member ? `${member.first_name} ${member.last_name}` : ""}
          onBack={() => setShowNote(false)}
          onExportPDF={() => window.print()}
        />
      </AiToolsSubPage>
    );
  }

  return (
    <AiToolsSubPage title="Pre-consultation Notes">
      <div className="max-w-2xl">
        <PreConsultationCard
          memberId={memberId}
          memberFirstName=""
          existingNote={note}
          onNoteReady={setNote}
          onViewNote={() => setShowNote(true)}
        />
      </div>
    </AiToolsSubPage>
  );
}
