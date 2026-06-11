import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { PreConsultationCard } from "@/components/members/pre-consultation-card";
import { PreConsultationNoteViewer } from "@/components/members/insight-report-viewer";
import { getLatestPreConsultationNote, getMember } from "@/lib/api/members";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { GeneratedInsight } from "@/lib/api/members";

export default function AiToolsPreConsultPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [note, setNote] = useState<GeneratedInsight | null>(null);
  const [showNote, setShowNote] = useState(false);
  const [member, setMember] = useState<FamilyMemberResponse | null>(null);

  useEffect(() => {
    if (!memberId) return;
    getLatestPreConsultationNote(memberId)
      .then((res: { note: GeneratedInsight | null }) => setNote(res.note))
      .catch(() => setNote(null));
    getMember(memberId)
      .then(setMember)
      .catch(() => setMember(null));
  }, [memberId]);

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
