import type { SmartRecommendation } from "@/lib/types/smart-report";
import { cn } from "@/lib/utils";

/**
 * Apollo SmartReport-style "Next steps" — a numbered list with priority-tinted
 * number circles. High → red, medium → amber, low → gray. Light-document palette.
 */
const ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
const PRIORITY: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-gray-100 text-gray-600",
};

export function RecommendationList({ recs }: { recs: SmartRecommendation[] }) {
  const sorted = [...recs].sort(
    (a, b) => (ORDER[a.priority ?? ""] ?? 3) - (ORDER[b.priority ?? ""] ?? 3)
  );
  return (
    <div className="space-y-3">
      {sorted.map((r, i) => (
        <div key={i} className="flex gap-3">
          <span
            className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold",
              PRIORITY[r.priority ?? ""] ?? "bg-gray-100 text-gray-600"
            )}
          >
            {i + 1}
          </span>
          <div className="pt-0.5">
            <p className="text-[13px] leading-snug text-gray-900">
              <span className="font-medium">{r.action}</span>
              {r.category && (
                <span className="ml-1.5 text-[11px] uppercase tracking-wide text-gray-400">
                  · {r.category}
                </span>
              )}
            </p>
            {r.reasoning && (
              <p className="mt-0.5 text-[12px] leading-snug text-gray-500">{r.reasoning}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
