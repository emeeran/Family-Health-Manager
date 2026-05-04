import { useState } from "react";
import type { MemberScore } from "@/lib/types/dashboard";

interface ScoreBreakdownProps {
  breakdown: Record<string, { score: number; max: number; label: string }>;
  total: number;
  compact?: boolean;
}

const COMPONENT_COLORS: Record<string, string> = {
  bmi: "bg-blue-500",
  conditions: "bg-emerald-500",
  labs: "bg-purple-500",
  meds: "bg-amber-500",
  profile: "bg-teal-500",
  recency: "bg-gray-400",
};

const COMPONENT_HOVER_COLORS: Record<string, string> = {
  bmi: "bg-blue-600",
  conditions: "bg-emerald-600",
  labs: "bg-purple-600",
  meds: "bg-amber-600",
  profile: "bg-teal-600",
  recency: "bg-gray-500",
};

const TOOLTIP_COLORS: Record<string, string> = {
  bmi: "text-blue-600",
  conditions: "text-emerald-600",
  labs: "text-purple-600",
  meds: "text-amber-600",
  profile: "text-teal-600",
  recency: "text-gray-600",
};

type TooltipState = { key: string; label: string; score: number; max: number } | null;

export function ScoreBreakdown({ breakdown, total, compact }: ScoreBreakdownProps) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const entries = Object.entries(breakdown);
  const totalMax = entries.reduce((sum, [, v]) => sum + v.max, 0);

  if (entries.length === 0 || totalMax === 0) {
    return (
      <div className="flex items-center gap-3 py-1">
        <div className="h-3 flex-1 rounded-full bg-muted" />
        <span className="text-sm font-bold text-muted-foreground">{total}/100</span>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <div className="flex h-4 w-full overflow-hidden rounded-full bg-muted">
          {entries.map(([key, val]) => {
            const widthPct = (val.max / totalMax) * 100;
            const fillPct = val.max > 0 ? (val.score / val.max) * 100 : 0;
            const isActive = activeKey === key;
            return (
              <div
                key={key}
                className="relative group/segment"
                style={{ width: `${widthPct}%` }}
                onMouseEnter={() => {
                  setTooltip({ key, label: val.label, score: val.score, max: val.max });
                  setActiveKey(key);
                }}
                onMouseLeave={() => {
                  setTooltip(null);
                  setActiveKey(null);
                }}
                onClick={() => {
                  if (tooltip?.key === key) {
                    setTooltip(null);
                    setActiveKey(null);
                  } else {
                    setTooltip({ key, label: val.label, score: val.score, max: val.max });
                    setActiveKey(key);
                  }
                }}
              >
                {/* Background track */}
                <div className="absolute inset-0 bg-muted-foreground/10" />
                {/* Filled portion */}
                <div
                  className={`absolute inset-y-0 left-0 transition-all duration-300 ${isActive ? COMPONENT_HOVER_COLORS[key] || "bg-gray-500" : COMPONENT_COLORS[key] || "bg-gray-400"}`}
                  style={{ width: `${fillPct}%` }}
                />
              </div>
            );
          })}
        </div>

        {/* Tooltip */}
        {tooltip && (
          <div className="absolute -top-10 left-1/2 -translate-x-1/2 z-10 pointer-events-none rounded-lg border bg-popover/95 backdrop-blur-sm px-3 py-1.5 shadow-md text-xs whitespace-nowrap">
            <span className={`font-semibold ${TOOLTIP_COLORS[tooltip.key] || ""}`}>
              {tooltip.label}
            </span>
            <span className="text-muted-foreground ml-1.5">
              {tooltip.score}/{tooltip.max}
            </span>
          </div>
        )}
      </div>

      {/* Legend + total */}
      {!compact && (
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {entries.map(([key, val]) => (
              <div key={key} className="flex items-center gap-1">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${COMPONENT_COLORS[key] || "bg-gray-400"}`}
                />
                <span className="text-[10px] text-muted-foreground font-medium">
                  {val.label} {val.score}/{val.max}
                </span>
              </div>
            ))}
          </div>
          <span className="text-sm font-bold shrink-0 ml-2">{total}/100</span>
        </div>
      )}
    </div>
  );
}
