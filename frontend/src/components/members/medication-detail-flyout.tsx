import { useCallback, useEffect, useState } from "react";
import {
  Eye,
  ExternalLink,
  Info,
  AlertTriangle,
  BookOpen,
  Stethoscope,
  Replace,
  CheckCircle2,
  HelpCircle,
  Loader2,
  XCircle,
} from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  getDrugAdverseEvents,
  getDrugEducation,
  getDrugIndication,
  getDrugLabel,
  getDrugSubstitutes,
  validateDrugInfo,
} from "@/lib/api/members";
import type { ActiveMedication } from "@/lib/types/member";
import type { VerificationResult } from "@/lib/types/message";
import type {
  AdverseEventReaction,
  DailyMedLabel,
  DrugIndication,
  DrugLabelSummary,
  MedlinePlusTopic,
  SubstituteDrug,
} from "@/lib/types/member";
import { TIMING_OPTIONS } from "@/lib/record-type-configs";

interface MedicationDetailFlyoutProps {
  memberId: string;
  med: ActiveMedication;
}

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "done";
      label: DrugLabelSummary | null;
      events: AdverseEventReaction[];
      edu: { medlineplus: MedlinePlusTopic[]; dailymed: DailyMedLabel[] };
      substitutes: SubstituteDrug[];
      indication: DrugIndication | null;
    }
  | { status: "error"; message: string };

const TIMING_FALLBACK: Record<string, string> = {
  before_food: "Before food",
  after_food: "After food",
  with_food: "With food",
  empty_stomach: "Empty stomach",
  bedtime: "Bedtime",
  sos: "SOS",
  stat: "Stat",
};

function timingLabel(t: string): string {
  return TIMING_OPTIONS.find((o) => o.value === t)?.label ?? TIMING_FALLBACK[t] ?? t;
}

export function MedicationDetailFlyout({ memberId, med }: MedicationDetailFlyoutProps) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [validating, setValidating] = useState(false);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    setVerification(null);
    try {
      const [labelRes, eventsRes, eduRes, subsRes, indRes] = await Promise.all([
        getDrugLabel(memberId, med.medicine),
        getDrugAdverseEvents(memberId, med.medicine),
        getDrugEducation(memberId, med.medicine),
        getDrugSubstitutes(memberId, med.medicine),
        getDrugIndication(memberId, med.medicine),
      ]);
      const label = labelRes.label;
      const events = eventsRes.events;
      const substitutes = subsRes.substitutes;
      const indication = indRes.indication;
      setState({
        status: "done",
        label,
        events,
        edu: { medlineplus: eduRes.medlineplus, dailymed: eduRes.dailymed },
        substitutes,
        indication,
      });
      // Best-effort second-model check that the content matches this medicine.
      // Never blocks the flyout — the badge resolves after the content shows.
      setValidating(true);
      validateDrugInfo(memberId, { medicine: med.medicine, indication, label, events, substitutes })
        .then((r) => setVerification(r.verification))
        .catch(() => setVerification(null))
        .finally(() => setValidating(false));
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof Error ? err.message : "Failed to load medicine details",
      });
    }
  }, [memberId, med.medicine]);

  // Fetch on open; reset on close so a stale payload never lingers.
  useEffect(() => {
    if (open) load();
    else {
      setState({ status: "idle" });
      setVerification(null);
    }
  }, [open, load]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        type="button"
        title="Medicine details"
        className="inline-flex items-center justify-center h-5 w-5 rounded text-muted-foreground hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 transition-colors"
      >
        <Eye className="h-2.5 w-2.5" />
      </PopoverTrigger>
      <PopoverContent align="end" side="top" className="w-96 max-h-[420px] overflow-y-auto p-0">
        <div className="p-3 border-b">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-sm font-semibold uppercase leading-tight truncate">
                {med.medicine}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                {labelGenericOrType(state, med)}
              </div>
            </div>
            {med.type && (
              <Badge variant="secondary" className="text-[10px]">
                {med.type}
              </Badge>
            )}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <Detail label="Dose" value={med.dosage || "--"} mono />
            <Detail label="Timing" value={med.timing ? timingLabel(med.timing) : "--"} />
            <Detail label="Duration" value={med.duration || "--"} />
            <Detail label="Rx by" value={med.provider_name || "--"} />
          </div>
        </div>

        <div className="p-3 space-y-3 text-xs">
          {state.status === "loading" && <FlyoutSkeletons />}

          {state.status === "error" && <p className="text-xs text-destructive">{state.message}</p>}

          {state.status === "done" && (
            <>
              <ValidationChip verification={verification} validating={validating} />

              {state.indication &&
                (state.indication.indication || state.indication.contraindication) && (
                  <Section icon={<Stethoscope className="h-3 w-3" />} title="Indication (ABDM)">
                    <IndicationBody indication={state.indication} />
                  </Section>
                )}

              <Section icon={<Info className="h-3 w-3" />} title="Prescribing label (openFDA)">
                {state.label ? (
                  <LabelBody label={state.label} />
                ) : (
                  <Empty>Note not available for this name.</Empty>
                )}
              </Section>

              <Section
                icon={<AlertTriangle className="h-3 w-3" />}
                title="Frequently reported effects"
              >
                {state.events.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {state.events.slice(0, 10).map((e) => (
                      <Badge key={e.term} variant="outline" className="text-[10px] font-normal">
                        {e.term}
                        <span className="ml-1 text-muted-foreground tabular-nums">{e.count}</span>
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <Empty>No adverse-event data.</Empty>
                )}
              </Section>

              <Section icon={<BookOpen className="h-3 w-3" />} title="Patient education">
                {state.edu.medlineplus.length > 0 || state.edu.dailymed.length > 0 ? (
                  <ul className="space-y-1">
                    {state.edu.medlineplus.slice(0, 3).map((t) => (
                      <LinkRow key={t.url} href={t.url} title={t.title} />
                    ))}
                    {state.edu.dailymed.slice(0, 2).map((d) => (
                      <LinkRow key={d.setid} href={d.url} title={`Full label: ${d.title}`} />
                    ))}
                  </ul>
                ) : (
                  <Empty>No education links found.</Empty>
                )}
              </Section>

              {state.substitutes.length > 0 && (
                <Section icon={<Replace className="h-3 w-3" />} title="Substitutes (ABDM)">
                  <div className="flex flex-wrap gap-1">
                    {state.substitutes.slice(0, 12).map((s) => (
                      <Badge
                        key={s.id || s.name}
                        variant="outline"
                        className="text-[10px] font-normal"
                      >
                        {s.name}
                      </Badge>
                    ))}
                  </div>
                </Section>
              )}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function labelGenericOrType(state: LoadState, med: ActiveMedication): string {
  if (state.status === "done" && state.label) {
    const parts = [state.label.generic_name, state.label.drug_class].filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  return med.note || "Live lookups via openFDA / MedlinePlus";
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground/80">{label}</dt>
      <dd className={`truncate ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-1.5">
      <h4 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
      </h4>
      <div>{children}</div>
    </section>
  );
}

function LabelBody({ label }: { label: DrugLabelSummary }) {
  const entries = Object.entries(label.sections || {});
  const priority = [
    "indications_and_usage",
    "warnings_and_precautions",
    "dosage_and_administration",
    "adverse_reactions",
  ];
  const ordered = [
    ...priority.filter((k) => label.sections?.[k]).map((k) => [k, label.sections![k]] as const),
    ...entries.filter(([k]) => !priority.includes(k)),
  ].slice(0, 4);
  return (
    <div className="space-y-2">
      {ordered.map(([key, text]) => (
        <div key={key}>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground/80">
            {key.replace(/_/g, " ")}
          </div>
          <p className="line-clamp-4 text-[11px] leading-relaxed">{text}</p>
        </div>
      ))}
    </div>
  );
}

function IndicationBody({ indication }: { indication: DrugIndication }) {
  const meta = [indication.dose_form, ...(indication.routes || [])].filter(Boolean).join(" · ");
  const blocks: { label: string; text: string }[] = [];
  if (indication.indication) blocks.push({ label: "Indication", text: indication.indication });
  if (indication.contraindication)
    blocks.push({ label: "Contraindication", text: indication.contraindication });
  return (
    <div className="space-y-2">
      {meta && (
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground/80">{meta}</p>
      )}
      {blocks.map((b) => (
        <div key={b.label}>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground/80">
            {b.label}
          </div>
          <p className="line-clamp-4 text-[11px] leading-relaxed">{b.text}</p>
        </div>
      ))}
    </div>
  );
}

function LinkRow({ href, title }: { href: string; title: string }) {
  return (
    <li>
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400 hover:underline"
      >
        <ExternalLink className="h-3 w-3 shrink-0" />
        <span className="truncate">{title}</span>
      </a>
    </li>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] italic text-muted-foreground">{children}</p>;
}

function ValidationChip({
  verification,
  validating,
}: {
  verification: VerificationResult | null;
  validating: boolean;
}) {
  if (validating) {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Cross-checking content…
      </div>
    );
  }
  const status = verification?.status;
  const high = (verification?.warnings ?? []).filter((w) => w?.severity === "high").length;
  let Icon: typeof CheckCircle2 = HelpCircle;
  let label = "Not validated";
  let tone = "text-muted-foreground";
  if (status === "verified") {
    Icon = CheckCircle2;
    label = "Content verified";
    tone = "text-emerald-600";
  } else if (status === "warnings") {
    Icon = AlertTriangle;
    label = high ? `${high} high-severity flag${high > 1 ? "s" : ""}` : "Verified — with warnings";
    tone = "text-amber-600";
  } else if (status === "unverifiable") {
    Icon = HelpCircle;
    label = "Could not cross-check";
  } else if (status === "unvalidated" || status === "failed") {
    Icon = XCircle;
    label = "Cross-check unavailable";
  }
  return (
    <div className={`flex items-center gap-1.5 text-[10px] ${tone}`}>
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{label}</span>
      {verification?.verifier_provider && (
        <span className="ml-auto truncate text-muted-foreground/70">
          via {verification.verifier_provider}
        </span>
      )}
    </div>
  );
}

function FlyoutSkeletons() {
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
      <div className="space-y-1.5">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-3 w-full" />
      </div>
    </div>
  );
}
