import { useState } from "react";
import { ShieldAlert, ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { RiskFactor } from "@/lib/types/dashboard";

interface RiskCardProps {
  riskLevel: "low" | "moderate" | "high";
  factors?: RiskFactor[];
}

const riskConfig = {
  low: {
    dotClass: "bg-emerald-500",
    textClass: "text-emerald-700",
    badgeClass: "bg-emerald-100 text-emerald-800 border border-emerald-200",
    bg: "bg-emerald-50 border-emerald-200",
    label: "Low Risk",
  },
  moderate: {
    dotClass: "bg-amber-500",
    textClass: "text-amber-700",
    badgeClass: "bg-amber-100 text-amber-800 border border-amber-200",
    bg: "bg-amber-50 border-amber-200",
    label: "Moderate Risk",
  },
  high: {
    dotClass: "bg-red-500",
    textClass: "text-red-700",
    badgeClass: "bg-red-100 text-red-800 border border-red-200",
    bg: "bg-red-50 border-red-200",
    label: "High Risk",
  },
} as const;

const factorSeverityConfig = {
  high: "text-red-600",
  moderate: "text-amber-600",
  low: "text-blue-600",
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
    <div className={`inline-flex flex-col rounded-xl border p-4 gap-2.5 ${config.bg}`}>
      <div className="flex items-center gap-2.5">
        <ShieldAlert className={`h-5 w-5 ${config.textClass}`} />
        <Badge className={`text-sm font-bold px-3 py-1 ${config.badgeClass}`}>
          <span className={`inline-block h-2 w-2 rounded-full mr-1.5 ${config.dotClass}`} />
          {config.label}
        </Badge>
        {hasFactors && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-auto text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg hover:bg-background/50"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        )}
      </div>

      {expanded && hasFactors && (
        <div className="space-y-2 pt-2 border-t border-current/10">
          {factors.map((factor, idx) => (
            <div key={`${factor.factor}-${idx}`} className="flex items-start gap-2.5">
              <span
                className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${factorDotConfig[factor.severity] || "bg-gray-400"}`}
              />
              <div>
                <p className="text-sm font-semibold leading-tight">{factor.factor}</p>
                <p className="text-xs text-muted-foreground leading-tight mt-0.5">
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
