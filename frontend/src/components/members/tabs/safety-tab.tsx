/**
 * Safety tab — authoritative drug-information hub for a member.
 *
 * Three panels:
 *  1. Drug Interactions  — existing AI/DrugBank report (rendered with a source
 *                          badge: DrugBank "verified" vs "AI estimate").
 *  2. Recall Alerts      — FDA enforcement reports matching active meds (openFDA, free).
 *  3. Drug Information   — FDA label highlights + top adverse reactions per med.
 *
 * All external lookups degrade to empty states on failure — a panel going blank
 * is acceptable; a 500 on a health record is not.
 */

import { memo, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  Pill,
  RefreshCw,
  ShieldAlert,
  Stethoscope,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DrugInteractionReport } from "@/components/members/drug-interaction-report";
import { getDrugAdverseEvents, getDrugLabel, getDrugRecalls } from "@/lib/api/members";
import { ApiError } from "@/lib/api-client";
import type {
  ActiveMedication,
  AdverseEventReaction,
  DrugLabelSummary,
  DrugRecall,
  MemberDetailResponse,
} from "@/lib/types/member";

interface SafetyTabProps {
  data: MemberDetailResponse;
}

export const SafetyTab = memo(function SafetyTab({ data }: SafetyTabProps) {
  const memberId = data.member.id;
  const medications = data.active_medications ?? [];
  const medCount = medications.length;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/40 p-3">
        <Info className="h-4 w-4 mt-0.5 shrink-0 text-blue-600 dark:text-blue-400" />
        <p className="text-xs text-blue-800 dark:text-blue-300">
          Drug-safety data combines AI analysis with authoritative FDA recall, label, and
          adverse-event records (openFDA) — and DrugBank interactions when configured. This is for
          awareness only and does not replace advice from a prescribing clinician.
        </p>
      </div>

      <DrugInteractionReport memberId={memberId} medicationCount={medCount} />

      <DrugRecallsPanel memberId={memberId} medCount={medCount} />

      <DrugInfoLookup memberId={memberId} medications={medications} />
    </div>
  );
});

// ── Recall Alerts (openFDA /drug/enforcement) ────────────────────────

interface RecallsPanelProps {
  memberId: string;
  medCount: number;
}

function DrugRecallsPanel({ memberId, medCount }: RecallsPanelProps) {
  const [recalls, setRecalls] = useState<DrugRecall[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getDrugRecalls(memberId);
      setRecalls(result.recalls);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Session expired — please refresh and sign in again."
          : "Couldn't load recall data. Please retry."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberId]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-red-500" />
            FDA Recall Alerts
            {recalls && recalls.length > 0 && (
              <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-700 dark:bg-red-900/60 dark:text-red-300">
                {recalls.length}
              </span>
            )}
          </CardTitle>
          <Button
            onClick={load}
            size="sm"
            variant="ghost"
            disabled={loading}
            className="text-xs h-7"
          >
            {loading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {medCount === 0 ? (
          <EmptyHint text="No active medications to check against FDA recalls." />
        ) : loading ? (
          <LoadingRow label="Checking active medications against FDA recalls…" />
        ) : error ? (
          <ErrorRow message={error} />
        ) : recalls && recalls.length > 0 ? (
          <div className="space-y-2">
            {recalls.map((recall, idx) => (
              <RecallCard key={idx} recall={recall} />
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-3 py-3 px-3 rounded-lg bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <div>
              <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                No active recalls
              </p>
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                None of the {medCount} active medication{medCount !== 1 ? "s" : ""} match current
                FDA enforcement reports.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RecallCard({ recall }: { recall: DrugRecall }) {
  const classification = recall.classification?.startsWith("Class I")
    ? { label: "Class I", cls: "bg-red-600 text-white" }
    : recall.classification?.startsWith("Class II")
      ? { label: "Class II", cls: "bg-amber-500 text-white" }
      : recall.classification?.startsWith("Class III")
        ? { label: "Class III", cls: "bg-blue-500 text-white" }
        : null;
  return (
    <div className="rounded-lg border border-red-200 dark:border-red-900/60 p-3 bg-red-50/50 dark:bg-red-950/20">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <p className="text-sm font-semibold">{recall.product_description || recall.generic_name}</p>
        {classification && (
          <span
            className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold rounded ${classification.cls}`}
          >
            {classification.label}
          </span>
        )}
      </div>
      <p className="text-sm text-foreground/80 mt-1">{recall.reason_for_recall}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-2 text-[11px] text-muted-foreground">
        {recall.recalling_firm && <span>Firm: {recall.recalling_firm}</span>}
        {recall.status && <span>Status: {recall.status}</span>}
        {recall.recall_initiation_date && <span>Initiated: {recall.recall_initiation_date}</span>}
      </div>
    </div>
  );
}

// ── Drug Information Lookup (openFDA /drug/label + /drug/event) ──────

interface InfoLookupProps {
  memberId: string;
  medications: ActiveMedication[];
}

function DrugInfoLookup({ memberId, medications }: InfoLookupProps) {
  const [selected, setSelected] = useState<string>("");
  const medicine = useMemo(
    () =>
      medications.find((m) => m.medicine === selected)?.medicine ?? medications[0]?.medicine ?? "",
    [medications, selected]
  );

  const [label, setLabel] = useState<DrugLabelSummary | null>(null);
  const [events, setEvents] = useState<AdverseEventReaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!medicine) {
      setLabel(null);
      setEvents([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getDrugLabel(memberId, medicine), getDrugAdverseEvents(memberId, medicine)])
      .then(([labelResp, eventsResp]) => {
        if (cancelled) return;
        setLabel(labelResp.label);
        setEvents(eventsResp.events);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status === 401
            ? "Session expired — please refresh and sign in again."
            : "Couldn't load label/adverse-event data for this medication."
        );
        setLabel(null);
        setEvents([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [memberId, medicine]);

  const sectionLabels: Record<string, string> = {
    indications_and_usage: "Uses",
    warnings_and_cautions: "Warnings",
    boxed_warning: "Boxed Warning",
    drug_interactions: "Drug Interactions",
    dosage_and_administration: "Dosage",
    contraindications: "Contraindications",
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Stethoscope className="h-4 w-4 text-violet-500" />
          FDA Drug Information
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {medications.length === 0 ? (
          <EmptyHint text="Add an active medication to look up its FDA label and reported side effects." />
        ) : (
          <>
            <select
              value={medicine}
              onChange={(e) => setSelected(e.target.value)}
              className="w-full max-w-sm mb-3 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {medications.map((m) => (
                <option key={`${m.record_id}-${m.prescription_index}`} value={m.medicine}>
                  {m.medicine}
                </option>
              ))}
            </select>

            {loading ? (
              <LoadingRow label="Fetching FDA label and adverse-event reports…" />
            ) : error ? (
              <ErrorRow message={error} />
            ) : (
              <div className="space-y-3">
                {label ? (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Pill className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-sm font-semibold">
                        {label.brand_name ? `${label.brand_name} (` : ""}
                        {label.generic_name}
                        {label.brand_name ? ")" : ""}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {Object.entries(label.sections).map(([key, text]) => (
                        <details
                          key={key}
                          className="rounded-md border border-border bg-muted/30 group"
                          open={key === "boxed_warning"}
                        >
                          <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold flex items-center gap-2">
                            {key === "boxed_warning" && (
                              <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
                            )}
                            {sectionLabels[key] ?? key.replace(/_/g, " ")}
                          </summary>
                          <p className="px-3 pb-3 text-xs text-foreground/80 whitespace-pre-wrap leading-relaxed">
                            {truncate(text, 1200)}
                          </p>
                        </details>
                      ))}
                    </div>
                  </div>
                ) : (
                  <EmptyHint text="No FDA label found for this medication." />
                )}

                {events.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold mb-1.5 text-muted-foreground">
                      Most-reported adverse reactions (FAERS)
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {events.map((ev) => (
                        <span
                          key={ev.term}
                          className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px]"
                          title={`${ev.count} reports`}
                        >
                          {ev.term}
                          <span className="text-muted-foreground">{ev.count}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── shared bits ──────────────────────────────────────────────────────

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-4">
      <Loader2 className="h-4 w-4 animate-spin text-foreground/40" />
      <span className="text-sm text-foreground/60">{label}</span>
    </div>
  );
}

function ErrorRow({ message }: { message: string }) {
  return (
    <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive font-medium">
      {message}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <p className="text-xs text-muted-foreground py-2">{text}</p>;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : text.slice(0, max).trimEnd() + "…";
}
