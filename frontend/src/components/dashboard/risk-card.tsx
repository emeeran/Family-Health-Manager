import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { RiskFactor } from "@/lib/types/dashboard";

interface RiskCardProps {
  riskLevel: "low" | "moderate" | "high";
  factors?: RiskFactor[];
}

const riskConfig = {
  low: {
    dotClass: "bg-emerald-500",
    badgeClass: "bg-emerald-100 text-emerald-800 border border-emerald-200",
    label: "Low Risk",
  },
  moderate: {
    dotClass: "bg-amber-500",
    badgeClass: "bg-amber-100 text-amber-800 border border-amber-200",
    label: "Moderate Risk",
  },
  high: {
    dotClass: "bg-red-500",
    badgeClass: "bg-red-100 text-red-800 border border-red-200",
    label: "High Risk",
  },
} as const;

const factorDotConfig = {
  high: "bg-red-500",
  moderate: "bg-amber-500",
  low: "bg-blue-500",
} as const;

export function RiskCard({ riskLevel, factors }: RiskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const config = riskConfig[riskLevel];
  const hasFactors = factors && factors.length > 0;

  return (
    <div className="inline-flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <Badge className={`text-xs font-bold px-2 py-0.5 ${config.badgeClass}`}>
          <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1 ${config.dotClass}`} />
          {config.label}
        </Badge>
        {hasFactors && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground p-0.5"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
        )}
      </div>

      {expanded && hasFactors && (
        <div className="space-y-1.5 pl-1">
          {factors.map((factor, idx) => (
            <div key={`${factor.factor}-${idx}`} className="flex items-start gap-2">
              <span
                className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${factorDotConfig[factor.severity] || "bg-gray-400"}`}
              />
              <div>
                <p className="text-xs font-semibold leading-tight">{factor.factor}</p>
                <p className="text-[11px] text-muted-foreground leading-tight">
                  {factor.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
