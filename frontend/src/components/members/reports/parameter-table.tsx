import { CheckCircle2 } from "lucide-react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { LabParameter, OrganDetail } from "@/lib/types/smart-report";
import { cn } from "@/lib/utils";

/**
 * Apollo SmartReport-style "Parameters in detail" table.
 * Columns: Parameter · Recent · Past. Status is a colored dot before the
 * recent value (green check / amber / red). Trend is a WORSENED/IMPROVED tag
 * right-aligned in the name column. A count summary sits in the section header.
 * Light-document palette (always on the white report page).
 */
const DOT: Record<string, string> = {
  borderline: "bg-amber-500",
  out_of_range: "bg-red-500",
  critical: "bg-red-700",
};

const TREND: Record<string, { label: string; cls: string }> = {
  improved: { label: "Improved", cls: "text-emerald-600" },
  further_decreased: { label: "Worsened", cls: "text-red-500" },
  new_abnormal: { label: "Worsened", cls: "text-red-500" },
};

function StatusDot({ status }: { status?: string | null }) {
  if (status === "in_range")
    return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  return (
    <span className={cn("h-2 w-2 shrink-0 rounded-full", DOT[status ?? ""] ?? "bg-gray-300")} />
  );
}

function pastValue(p: LabParameter): string {
  const prev = p.previous_values ?? [];
  if (prev.length === 0) return "—";
  return prev[prev.length - 1].value ?? "—";
}

export function ParameterTable({ detail }: { detail: OrganDetail }) {
  const params = detail.parameters ?? [];
  if (params.length === 0) return null;
  const out = params.filter((p) => p.status === "out_of_range" || p.status === "critical").length;
  const borderline = params.filter((p) => p.status === "borderline").length;
  const inRange = params.filter((p) => p.status === "in_range").length;

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 bg-gray-50 px-3 py-2">
        <span className="text-sm font-bold text-gray-900">{detail.system ?? "Other"}</span>
        <span className="text-[11px] text-gray-500">
          {out > 0 && (
            <span className="mr-2.5">
              <span className="text-red-500">●</span> {out} out of range
            </span>
          )}
          {borderline > 0 && (
            <span className="mr-2.5">
              <span className="text-amber-500">●</span> {borderline} borderline
            </span>
          )}
          {inRange > 0 && <span className="text-emerald-600">✓ {inRange} in range</span>}
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow className="border-gray-200 hover:bg-transparent">
            <TableHead className="h-8 px-3 text-[10px] font-bold uppercase tracking-wide text-gray-500">
              Parameter
            </TableHead>
            <TableHead className="h-8 px-3 text-[10px] font-bold uppercase tracking-wide text-gray-500">
              Recent
            </TableHead>
            <TableHead className="h-8 px-3 text-[10px] font-bold uppercase tracking-wide text-gray-500">
              Past
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {params.map((p, i) => {
            const trend = p.trend ? TREND[p.trend] : undefined;
            return (
              <TableRow key={i} className="border-gray-100 text-[13px] text-gray-900">
                <TableCell className="px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{p.name}</span>
                    {trend && (
                      <span
                        className={cn(
                          "shrink-0 text-[10px] font-bold uppercase tracking-wide",
                          trend.cls
                        )}
                      >
                        {trend.label}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="px-3 py-2">
                  <span className="flex items-center gap-1.5 tabular-nums">
                    <StatusDot status={p.status} />
                    <span
                      className={cn(
                        p.status === "out_of_range" && "font-semibold",
                        p.status === "critical" && "font-bold"
                      )}
                    >
                      {p.value ?? "—"}
                    </span>
                    {p.unit && <span className="text-[10px] text-gray-500">{p.unit}</span>}
                  </span>
                </TableCell>
                <TableCell className="px-3 py-2 text-gray-500 tabular-nums">
                  {pastValue(p)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
