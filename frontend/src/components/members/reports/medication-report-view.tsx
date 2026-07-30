/**
 * Structured render of a Medication Report (theme 2). Shown when the backend
 * parsed the AI JSON payload; the dialog falls back to markdown `response` when
 * this is absent. Light-document palette to match the other report viewers.
 */
import { Pill, AlertTriangle, ShieldAlert, CalendarClock, Lightbulb, Info } from "lucide-react";
import type {
  MedicationReportData,
  Medicine,
  MedicationInteraction,
  MedicationRecommendation,
} from "@/lib/types/medication-report";
import { cn } from "@/lib/utils";

function Section({
  icon: Icon,
  title,
  accent,
  children,
}: {
  icon: typeof Pill;
  title: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <span
          className="flex h-6 w-6 items-center justify-center rounded-md"
          style={{ backgroundColor: `${accent}1a` }}
        >
          <Icon className="h-3.5 w-3.5" style={{ color: accent }} />
        </span>
        <h3 className="text-[12px] font-bold uppercase tracking-wide text-gray-800">{title}</h3>
      </div>
      {children}
    </section>
  );
}

const SEV: Record<string, { wrap: string; badge: string; label: string }> = {
  high: { wrap: "bg-red-50 border-red-200", badge: "bg-red-100 text-red-700", label: "High" },
  moderate: {
    wrap: "bg-amber-50 border-amber-200",
    badge: "bg-amber-100 text-amber-700",
    label: "Moderate",
  },
  low: { wrap: "bg-gray-50 border-gray-200", badge: "bg-gray-200 text-gray-700", label: "Low" },
};

function sevOf(s?: string | null) {
  const k = (s ?? "").toLowerCase();
  if (k.startsWith("high")) return SEV.high;
  if (k.startsWith("mod") || k.startsWith("medium")) return SEV.moderate;
  if (k.startsWith("low")) return SEV.low;
  return null;
}

const PRIO: Record<string, { dot: string; label: string }> = {
  high: { dot: "bg-red-500", label: "High" },
  medium: { dot: "bg-amber-500", label: "Medium" },
  low: { dot: "bg-emerald-500", label: "Low" },
};

export function MedicationReportView({ report }: { report: MedicationReportData }) {
  const meds = report.medicines ?? [];
  const interactions = report.interactions ?? [];
  const recs = report.recommendations ?? [];
  const alerts = (report.safety_alerts ?? "").trim();
  const noAlerts = /no active recalls/i.test(alerts);

  return (
    <div className="space-y-5">
      {report.regimen_overview && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-2.5 text-[13px] leading-relaxed text-gray-800">
          {report.regimen_overview}
        </div>
      )}

      {meds.length > 0 && (
        <Section icon={Pill} title="Medicines" accent="#7c3aed">
          <div className="space-y-2">
            {meds.map((m: Medicine, i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-white p-3">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[13px] font-semibold text-gray-900">{m.name}</span>
                  {m.dose_schedule && (
                    <span className="text-[12px] text-gray-600">{m.dose_schedule}</span>
                  )}
                  {m.indication && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600">
                      {m.indication}
                    </span>
                  )}
                </div>
                {m.key_note && (
                  <p className="mt-1 text-[12px] leading-relaxed text-gray-600">{m.key_note}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {interactions.length > 0 && (
        <Section icon={AlertTriangle} title="Drug interactions" accent="#dc2626">
          <div className="space-y-2">
            {interactions.map((it: MedicationInteraction, i) => {
              const sev = sevOf(it.severity);
              return (
                <div
                  key={i}
                  className={cn(
                    "rounded-lg border p-3",
                    sev ? sev.wrap : "bg-white border-gray-200"
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold text-gray-900">
                      {it.pair || "Interaction"}
                    </span>
                    {it.severity && (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                          sev?.badge ?? "bg-gray-100 text-gray-600"
                        )}
                      >
                        {sev?.label ?? it.severity}
                      </span>
                    )}
                  </div>
                  {it.explanation && (
                    <p className="mt-1 text-[12px] leading-relaxed text-gray-700">
                      {it.explanation}
                    </p>
                  )}
                  {it.action && (
                    <p className="mt-1 text-[12px] font-medium text-gray-800">→ {it.action}</p>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {report.schedule_adherence && (
        <Section icon={CalendarClock} title="Schedule & adherence" accent="#0891b2">
          <p className="rounded-lg border border-gray-200 bg-white p-3 text-[12px] leading-relaxed text-gray-700">
            {report.schedule_adherence}
          </p>
        </Section>
      )}

      {alerts && (
        <Section icon={ShieldAlert} title="Safety alerts" accent={noAlerts ? "#16a34a" : "#dc2626"}>
          <div
            className={cn(
              "rounded-lg border p-3 text-[12px] leading-relaxed",
              noAlerts
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-red-200 bg-red-50 text-red-800"
            )}
          >
            {alerts}
          </div>
        </Section>
      )}

      {recs.length > 0 && (
        <Section icon={Lightbulb} title="Recommendations" accent="#0d9488">
          <ul className="space-y-1.5">
            {recs.map((r: MedicationRecommendation, i) => {
              const k = (r.priority ?? "").toLowerCase();
              const prio = k.startsWith("high")
                ? PRIO.high
                : k.startsWith("low")
                  ? PRIO.low
                  : PRIO.medium;
              return (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-lg border border-gray-200 bg-white p-2.5"
                >
                  <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", prio.dot)} />
                  <div>
                    {r.priority && (
                      <span className="mr-1.5 text-[10px] font-bold uppercase tracking-wide text-gray-400">
                        {prio.label}
                      </span>
                    )}
                    <span className="text-[12px] leading-relaxed text-gray-800">{r.action}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <p className="flex items-center gap-1 text-[11px] text-gray-400">
        <Info className="h-3 w-3" /> For information only — not medical advice. Verify with a
        clinician.
      </p>
    </div>
  );
}
