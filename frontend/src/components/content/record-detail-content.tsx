import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { StructuredDataDisplay } from "@/components/records/structured-data-display";
import { RecordAttachments } from "@/components/records/record-attachments";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { RECORD_TYPE_LABELS, GENDER_LABELS } from "@/lib/constants";
import { computeAge, formatDate } from "@/lib/utils";
import { deleteRecord, getRecord, getRecordInsight } from "@/lib/api/records";
import { streamRequest } from "@/lib/api-client";
import { toast } from "sonner";
import { Printer, Sparkles, RefreshCw, AlertTriangle } from "lucide-react";
import type { HealthRecordResponse, RecordInsight } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface RecordDetailContentProps {
  record: HealthRecordResponse;
  member: FamilyMemberResponse;
}

export function RecordDetailContent({ record: initialRecord, member }: RecordDetailContentProps) {
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [record, setRecord] = useState(initialRecord);
  const [insight, setInsight] = useState<RecordInsight | null>(null);
  const [insightLoading, setInsightLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamStage, setStreamStage] = useState("");
  const isLabReport = record.record_type === "lab_report";

  // Fetch AI insight on mount
  useEffect(() => {
    let cancelled = false;
    async function fetchInsight() {
      try {
        const res = await getRecordInsight(member.id, record.id);
        if (!cancelled) setInsight(res.insight);
      } catch {
        // Insight may not be ready yet (async generation)
      } finally {
        if (!cancelled) setInsightLoading(false);
      }
    }
    fetchInsight();
    return () => {
      cancelled = true;
    };
  }, [member.id, record.id]);

  // Poll for verification when status is pending
  useEffect(() => {
    if (!insight || insight.verification?.status !== "pending") return;
    let attempts = 0;
    const maxAttempts = 15;
    const interval = setInterval(async () => {
      attempts++;
      if (attempts >= maxAttempts) {
        clearInterval(interval);
        return;
      }
      try {
        const res = await getRecordInsight(member.id, record.id);
        if (res.insight?.verification?.status !== "pending") {
          setInsight(res.insight);
          clearInterval(interval);
        }
      } catch {
        /* continue polling */
      }
    }, 2000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insight?.verification?.status, member.id, record.id]);

  async function handleRegenerateInsight() {
    setRegenerating(true);
    setStreamText("");
    setStreamStage("Starting...");
    let accumulated = "";
    try {
      await streamRequest(`/members/${member.id}/records/${record.id}/regenerate-insight/stream`, {
        onEvent: (event) => {
          const e = event as Record<string, unknown>;
          const stage = e.stage as string;
          if (stage === "context") {
            setStreamStage((e.message as string) || "Preparing...");
          } else if (stage === "provider") {
            setStreamStage(`Generating via ${e.provider}...`);
          } else if (stage === "token") {
            accumulated += (e.content as string) || "";
            setStreamText(accumulated);
          } else if (stage === "complete") {
            // Refresh full insight from server (includes verification)
            const insightId = e.insight_id as string;
            const provider = e.provider as string;
            setInsight((prev) => ({
              id: insightId,
              prompt: prev?.prompt || "",
              response: accumulated,
              provider_used: provider,
              generated_at: new Date().toISOString(),
              verification: {
                status: "pending",
                claims_checked: 0,
                verifier_provider: "",
                summary: null,
                warnings: null,
                verified_at: "",
              },
            }));
            setStreamStage("");
            // Reload from server to get proper verification
            getRecordInsight(member.id, record.id)
              .then((res) => {
                if (res.insight) setInsight(res.insight);
              })
              .catch(() => {});
          } else if (stage === "error") {
            toast.error((e.message as string) || "Generation failed");
          }
        },
      });
      toast.success("AI insight regenerated");
    } catch {
      toast.error("Failed to regenerate insight");
    } finally {
      setRegenerating(false);
      setStreamStage("");
    }
  }

  async function refreshRecord() {
    try {
      const updated = await getRecord(member.id, record.id);
      setRecord(updated);
    } catch {
      /* keep current state */
    }
  }

  async function handleDelete() {
    try {
      await deleteRecord(member.id, record.id);
      toast.success("Record deleted");
      navigate(`/people/${member.id}?tab=records`);
    } catch {
      toast.error("Failed to delete record");
    }
  }

  const memberAge = computeAge(member.date_of_birth);
  const memberGender = GENDER_LABELS[member.gender] || member.gender;
  const memberName = `${member.first_name} ${member.last_name}`;

  // Shared props for StructuredDataDisplay
  const displayProps = {
    memberName,
    memberAge,
    memberGender,
    memberBloodGroup: member.blood_group || undefined,
    providerName: record.provider_name || undefined,
    recordDate: record.record_date,
    recordTime: record.record_time || undefined,
    diagnosis: record.diagnosis || undefined,
    nextReviewDate: record.next_review_date || undefined,
  };

  return (
    <div className="space-y-6">
      {/* Print-only header */}
      <div className="hidden print:block mb-6 pb-4 border-b-2 border-gray-900">
        <h1 className="text-xl font-bold">
          {memberName} — {RECORD_TYPE_LABELS[record.record_type]}
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          {formatDate(record.record_date)} &middot; {record.provider_name || "N/A"}
        </p>
      </div>

      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground print:hidden">
        <Link to="/people" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/people/${member.id}`} className="hover:underline">
          {memberName}
        </Link>
        <span>/</span>
        <Link to={`/people/${member.id}?tab=records`} className="hover:underline">
          Records
        </Link>
        <span>/</span>
        <span className="text-foreground">{RECORD_TYPE_LABELS[record.record_type]}</span>
      </div>

      {/* Title bar */}
      <div className="flex items-center justify-between print:hidden">
        <div className="flex items-center gap-3">
          <RecordTypeBadge type={record.record_type} />
          <h1 className="text-2xl font-bold">
            {record.diagnosis || RECORD_TYPE_LABELS[record.record_type]}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => window.print()} className="gap-1.5">
            <Printer className="h-3.5 w-3.5" />
            Export
          </Button>
          <Link to={`/people/${member.id}/records/${record.id}/edit`}>
            <Button variant="outline" size="sm">
              Edit
            </Button>
          </Link>
          <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
            Delete
          </Button>
        </div>
      </div>

      {/* ── Lab report: full-width professional view ── */}
      {isLabReport ? (
        <StructuredDataDisplay
          recordType={record.record_type}
          clinicalData={record.clinical_data}
          {...displayProps}
        />
      ) : (
        /* ── Other record types: full-width layout ── */
        <div>
          {/* Compact metadata bar */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground pb-3 mb-4 border-b border-gray-200 dark:border-gray-700 print:hidden">
            <span>{formatDate(record.record_date)}</span>
            {record.record_time && <span>{record.record_time}</span>}
            {record.provider_name && (
              <>
                <span className="opacity-40">·</span>
                <span>{record.provider_name}</span>
              </>
            )}
            {record.next_review_date && (
              <>
                <span className="opacity-40">·</span>
                <span>Next review {formatDate(record.next_review_date)}</span>
              </>
            )}
            <span className="ml-auto opacity-50">Created {formatDate(record.created_at)}</span>
          </div>

          {/* Clinical data — full width, no card */}
          <StructuredDataDisplay
            recordType={record.record_type}
            clinicalData={record.clinical_data}
            {...displayProps}
          />

          {record.prescription_text && (
            <div className="border-t border-gray-200 dark:border-gray-700 mt-4 pt-4">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Prescription
              </p>
              <p className="text-sm whitespace-pre-wrap">{record.prescription_text}</p>
            </div>
          )}
        </div>
      )}

      {/* AI Insight Card */}
      <Card className="border-blue-200 dark:border-blue-900 bg-blue-50/50 dark:bg-blue-950/20 print:hidden">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-500" />
              AI Health Insight
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={handleRegenerateInsight}
              disabled={regenerating || insightLoading}
            >
              <RefreshCw className={`h-3 w-3 ${regenerating ? "animate-spin" : ""}`} />
              {regenerating ? "Generating..." : "Regenerate"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {regenerating && streamText ? (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              {streamStage && (
                <p className="text-xs text-blue-500 font-medium mb-2">{streamStage}</p>
              )}
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{streamText}</div>
              <span className="inline-block w-1.5 h-4 bg-blue-400 animate-pulse ml-0.5 align-text-bottom" />
            </div>
          ) : insightLoading ? (
            <div className="space-y-2">
              <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
              <div className="h-4 bg-muted animate-pulse rounded w-1/2" />
              <div className="h-4 bg-muted animate-pulse rounded w-2/3" />
            </div>
          ) : insight ? (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{insight.response}</div>
              <div className="flex items-center gap-2 mt-3 pt-2 border-t border-blue-200 dark:border-blue-800">
                <p className="text-xs text-muted-foreground">
                  Generated by {insight.provider_used} &middot; {formatDate(insight.generated_at)}{" "}
                  &middot; Not medical advice
                </p>
                <VerificationBadge verification={insight.verification} />
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertTriangle className="h-4 w-4" />
              <span>
                AI insight is being generated.{" "}
                <button
                  className="text-blue-500 hover:underline"
                  onClick={handleRegenerateInsight}
                  disabled={regenerating}
                >
                  Generate now
                </button>
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Original Documents */}
      <RecordAttachments
        recordId={record.id}
        attachments={record.attachments || []}
        onAttachmentsChanged={refreshRecord}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Record"
        description="Are you sure you want to delete this record? This action cannot be undone."
        onConfirm={handleDelete}
      />
    </div>
  );
}
