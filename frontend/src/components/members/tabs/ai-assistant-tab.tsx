import { memo, useState, Suspense } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ShieldCheck, Bell } from "lucide-react";
import { exportHTMLToPDF } from "@/lib/pdf-export";
import { InsightCard } from "@/components/members/insight-card";
import { PreConsultationCard } from "@/components/members/pre-consultation-card";
import { DrugInteractionReport } from "@/components/members/drug-interaction-report";
import { ProvidersUhidCard } from "@/components/members/providers-uhid-card";
import { VaccinationsSection } from "@/components/members/vaccinations-section";
import {
  InsightReport,
  PreConsultationNoteViewer,
  parseSections,
} from "@/components/members/insight-report-viewer";
import { createPreventiveReminder } from "@/lib/api/members";
import { formatDate } from "@/lib/utils";
import { GENDER_LABELS } from "@/lib/constants";
import { toast } from "sonner";
import type { MemberDetailResponse, PreventiveRecommendation } from "@/lib/types/member";
import type { GeneratedInsight } from "@/lib/api/members";
import type { VerificationResult } from "@/lib/types/message";

/* ── Preventive Care Table ── */

const PRIORITY_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-blue-500",
};
const PRIORITY_LABEL: Record<string, string> = {
  high: "Due now",
  medium: "Upcoming",
  low: "Optional",
};

function PreventiveCareTable({
  recommendations,
  memberId,
}: {
  recommendations: PreventiveRecommendation[];
  memberId: string;
}) {
  const [settingReminder, setSettingReminder] = useState<string | null>(null);

  async function handleSetReminder(rec: PreventiveRecommendation) {
    setSettingReminder(rec.title);
    try {
      await createPreventiveReminder(memberId, rec);
      toast.success(`Reminder set: ${rec.title}`);
    } catch {
      toast.error("Failed to create reminder");
    } finally {
      setSettingReminder(null);
    }
  }

  if (recommendations.length === 0) return null;

  return (
    <Card className="shadow-none">
      <CardContent className="pt-4 pb-3">
        <div className="text-sm font-semibold flex items-center gap-2 mb-3">
          <ShieldCheck className="h-4 w-4 text-blue-500" />
          Preventive Care
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-auto">
            {recommendations.length}
          </Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-[10px] text-muted-foreground uppercase tracking-wider">
                <th className="py-2 px-3 font-medium">Priority</th>
                <th className="py-2 px-3 font-medium">Recommendation</th>
                <th className="py-2 px-3 font-medium hidden sm:table-cell">Details</th>
                <th className="py-2 px-3 font-medium hidden md:table-cell">Frequency</th>
                <th className="py-2 px-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((rec, i) => (
                <tr
                  key={i}
                  className="border-b last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-2 px-3">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${PRIORITY_DOT[rec.priority] || PRIORITY_DOT.low}`}
                      />
                      <span className="text-xs font-medium capitalize">
                        {PRIORITY_LABEL[rec.priority] || rec.priority}
                      </span>
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <span className="font-medium text-xs">{rec.title}</span>
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden sm:table-cell">
                    {rec.description}
                  </td>
                  <td className="py-2 px-3 text-xs text-muted-foreground hidden md:table-cell">
                    {rec.due_interval_months === 0
                      ? "One-time"
                      : rec.due_interval_months >= 12
                        ? `Every ${rec.due_interval_months / 12}y`
                        : `Every ${rec.due_interval_months}mo`}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[11px] px-2"
                      disabled={settingReminder === rec.title}
                      onClick={() => handleSetReminder(rec)}
                    >
                      <Bell className="h-3 w-3 mr-1" />
                      {settingReminder === rec.title ? "..." : "Remind"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── AI Assistant Tab ── */

interface AiAssistantTabProps {
  data: MemberDetailResponse;
}

export const AiAssistantTab = memo(function AiAssistantTab({ data }: AiAssistantTabProps) {
  const {
    member,
    active_medications,
    provider_assignments,
    latest_insight,
    latest_preconsult_note,
    drug_interactions,
    preventive_recommendations,
    vaccinations,
  } = data;

  const [insight, setInsight] = useState<GeneratedInsight | null>(
    latest_insight
      ? {
          id: latest_insight.id,
          response: latest_insight.response,
          provider_used: latest_insight.provider_used,
          generated_at: latest_insight.generated_at,
          verification: latest_insight.verification as VerificationResult | null,
        }
      : null
  );
  const [preConsultNote, setPreConsultNote] = useState<GeneratedInsight | null>(
    latest_preconsult_note
      ? {
          id: latest_preconsult_note.id,
          response: latest_preconsult_note.response,
          provider_used: latest_preconsult_note.provider_used,
          generated_at: latest_preconsult_note.generated_at,
          verification: latest_preconsult_note.verification as VerificationResult | null,
        }
      : null
  );
  const [showPreConsult, setShowPreConsult] = useState(false);
  const [showReport, setShowReport] = useState(false);

  async function handlePreConsultPDF() {
    if (!preConsultNote) return;
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const mn = `${member.first_name} ${member.last_name}`;
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const dateStr = new Date(preConsultNote.generated_at).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const sections = parseSections(preConsultNote.response);
    const sectionHtml = sections
      .map(
        (s) =>
          `<div style="margin-bottom:14px;padding-left:12px;border-left:3px solid #14B8A6"><div style="font-weight:bold;font-size:11px;margin-bottom:4px;color:#0f766e">${esc(s.title)}</div><div style="font-size:10px;line-height:1.7;color:#374151">${esc(
            s.body
          )
            .replace(/\[ \]/g, "☐")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>")}</div></div>`
      )
      .join("");
    const html = `<!DOCTYPE html><html><head><title>Pre-Consultation Note — ${esc(mn)}</title><style>@page { margin: 0.75in 1in; } * { margin: 0; box-sizing: border-box; } body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; font-size: 11px; }</style></head>
<body><div style="text-align:center;margin-bottom:16px;border-bottom:2px solid #14B8A6;padding-bottom:12px"><div style="font-size:14px;font-weight:bold">${esc(mn)} — Pre-Consultation Note</div><div style="font-size:10px;color:#6b7280;margin-top:4px">${dateStr} &middot; via ${esc(preConsultNote.provider_used)}</div><div style="font-size:9px;color:#9ca3af;margin-top:2px">Exported ${now}</div></div>
${sectionHtml}
<div style="margin-top:16px;padding-top:6px;border-top:1px solid #d1d5db;font-size:9px;color:#9ca3af">AI-generated for informational purposes only. Review with your healthcare provider.</div></body></html>`;
    try {
      await exportHTMLToPDF(html, `pre-consultation-${mn}-${dateStr}.pdf`);
    } catch {
      const win = window.open("", "_blank");
      if (!win) return;
      win.document.write(html);
      win.document.close();
      setTimeout(() => win.print(), 200);
    }
  }

  function handleInsightReady(result: GeneratedInsight) {
    setInsight(result);
    setShowReport(true);
  }

  if (showPreConsult && preConsultNote) {
    return (
      <PreConsultationNoteViewer
        response={preConsultNote.response}
        provider={preConsultNote.provider_used}
        generatedAt={preConsultNote.generated_at}
        verification={preConsultNote.verification}
        memberName={`${member.first_name} ${member.last_name}`}
        onBack={() => setShowPreConsult(false)}
        onExportPDF={handlePreConsultPDF}
      />
    );
  }

  if (showReport && insight) {
    return (
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-12">
            <p className="text-muted-foreground">Loading report...</p>
          </div>
        }
      >
        <InsightReport
          response={insight.response}
          provider={insight.provider_used}
          generatedAt={insight.generated_at}
          verification={insight.verification}
          memberName={`${member.first_name} ${member.last_name}`}
          memberDob={formatDate(member.date_of_birth)}
          memberGender={GENDER_LABELS[member.gender]}
          onBack={() => setShowReport(false)}
        />
      </Suspense>
    );
  }

  return (
    <div className="space-y-3">
      {/* AI Tools */}
      <div className="grid gap-3 md:grid-cols-2">
        <PreConsultationCard
          memberId={member.id}
          memberFirstName={member.first_name}
          existingNote={preConsultNote}
          onNoteReady={setPreConsultNote}
          onViewNote={() => setShowPreConsult(true)}
        />
        <InsightCard
          memberId={member.id}
          memberFirstName={member.first_name}
          existingInsight={insight}
          onInsightReady={handleInsightReady}
          onViewReport={() => setShowReport(true)}
        />
      </div>

      {/* Safety & Care */}
      <div className="grid gap-3 md:grid-cols-2">
        <DrugInteractionReport
          memberId={member.id}
          medicationCount={active_medications?.length ?? 0}
        />
        <VaccinationsSection memberId={member.id} />
      </div>

      {/* Preventive Care */}
      <PreventiveCareTable recommendations={preventive_recommendations} memberId={member.id} />

      {/* Providers */}
      <ProvidersUhidCard memberId={member.id} assignments={provider_assignments} />
    </div>
  );
});
