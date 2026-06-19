import type { ParameterInFocus } from "@/lib/types/smart-report";

/**
 * Apollo SmartReport-style key-finding bullet — a colored marker + parameter
 * name with its trend note, the clinical significance, and an arrow-led
 * recommendation. Light-document palette (always on the white report page).
 */
export function FocusCard({ param }: { param: ParameterInFocus }) {
  return (
    <div className="flex gap-2">
      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
      <div className="min-w-0">
        <p className="text-[13px] leading-snug text-gray-900">
          <span className="font-semibold">{param.name}</span>
          {param.trend_note && <span className="text-gray-600"> — {param.trend_note}</span>}
        </p>
        {param.significance && (
          <p className="mt-0.5 text-[12px] leading-snug text-gray-500">{param.significance}</p>
        )}
        {param.recommendation && (
          <p className="mt-0.5 text-[12px] leading-snug text-gray-700">→ {param.recommendation}</p>
        )}
      </div>
    </div>
  );
}
