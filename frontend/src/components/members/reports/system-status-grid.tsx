import {
  Heart,
  Droplets,
  FlaskConical,
  Zap,
  Brain,
  Bone,
  Eye,
  ShieldCheck,
  Activity,
  type LucideIcon,
} from "lucide-react";
import type { SystemGlance } from "@/lib/types/smart-report";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "Blood Health": Droplets,
  "Heart Health": Heart,
  "GI & Liver": FlaskConical,
  "Kidney Health": Activity,
  "Blood Glucose": Zap,
  "Hormone Health": Brain,
  "Bone & Muscle": Bone,
  "Skin & Hair": Eye,
  "Immune System": ShieldCheck,
};

/**
 * Apollo SmartReport-style body-system cards. Each card: gray icon + bold
 * name + colored status label + subtitle + a thin colored gauge. Cards are
 * grouped into "Updated based on recent data" and "Other body systems".
 * Light-document palette (always rendered on the white report page).
 */
const STATUS: Record<string, { label: string; text: string; bar: string }> = {
  needs_attention: { label: "Needs attention", text: "text-red-600", bar: "bg-red-500" },
  ideal: { label: "All good", text: "text-emerald-600", bar: "bg-emerald-500" },
  no_data: { label: "No data found", text: "text-gray-500", bar: "bg-gray-300" },
};

function SystemCard({ s }: { s: SystemGlance }) {
  const Icon = (s.system && ICONS[s.system]) || Activity;
  const st = STATUS[s.status ?? ""] ?? STATUS.no_data;
  const total = s.parameters_total ?? 0;
  const oor = s.parameters_out_of_range ?? 0;
  const pct =
    total > 0 ? Math.round(((total - oor) / total) * 100) : s.status === "ideal" ? 100 : 0;
  const sub =
    total > 0
      ? s.status === "ideal"
        ? "All parameters in range"
        : `${oor} of ${total} out of range`
      : "Data for this system isn't available yet";
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-gray-400" />
        <span className="text-sm font-bold text-gray-900">{s.system ?? "Other"}</span>
      </div>
      <div className={cn("mt-1.5 text-[13px] font-semibold", st.text)}>{st.label}</div>
      <div className="mt-0.5 text-[11px] text-gray-500">{sub}</div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-gray-100">
        <div className={cn("h-full rounded-full", st.bar)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function SystemStatusGrid({ systems }: { systems: SystemGlance[] }) {
  const updated = systems.filter((s) => s.status !== "no_data");
  const other = systems.filter((s) => s.status === "no_data");
  const grouped = updated.length > 0 && other.length > 0;
  return (
    <div className="space-y-4">
      {updated.length > 0 && (
        <div>
          {grouped && (
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              Updated based on recent data
            </div>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {updated.map((s, i) => (
              <SystemCard key={s.system ?? i} s={s} />
            ))}
          </div>
        </div>
      )}
      {other.length > 0 && (
        <div>
          {grouped && (
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
              Other body systems
            </div>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {other.map((s, i) => (
              <SystemCard key={s.system ?? i} s={s} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
