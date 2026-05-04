import { Pill, AlertTriangle, Package } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { MedicationSummary } from "@/lib/types/dashboard";

interface MedicationSummaryWidgetProps {
  summary: MedicationSummary;
  memberNames: Record<string, string>;
}

function urgencyBadge(days: number): { label: string; cls: string } {
  if (days <= 3) return { label: "Urgent", cls: "bg-red-100 text-red-800 border border-red-200" };
  if (days <= 7)
    return { label: "Soon", cls: "bg-amber-100 text-amber-800 border border-amber-200" };
  return { label: "OK", cls: "bg-emerald-100 text-emerald-800 border border-emerald-200" };
}

export function MedicationSummaryWidget({
  summary,
  memberNames: _memberNames,
}: MedicationSummaryWidgetProps) {
  const { total_active_medications, members_with_medications, refill_reminders } = summary;
  const topRefills = refill_reminders.slice(0, 4);

  return (
    <Card className="overflow-hidden shadow-sm">
      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="text-base font-semibold flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/10">
            <Pill className="h-4 w-4 text-violet-600" />
          </div>
          Medications
        </div>
      </div>
      <CardContent>
        {total_active_medications === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-foreground/70">
            <Pill className="h-8 w-8 text-muted-foreground/30" />
            <p className="text-sm font-medium">No active medications</p>
          </div>
        ) : (
          <>
            {/* Stat numbers */}
            <div className="grid grid-cols-3 gap-2.5 mb-4">
              <div className="flex flex-col items-center rounded-xl bg-violet-500/10 border border-violet-200/50 px-2 py-2.5">
                <Package className="h-4 w-4 text-violet-600 mb-1" />
                <span className="text-xl font-bold text-violet-700">
                  {total_active_medications}
                </span>
                <span className="text-[11px] text-muted-foreground font-medium">Active</span>
              </div>
              <div className="flex flex-col items-center rounded-xl bg-blue-500/10 border border-blue-200/50 px-2 py-2.5">
                <Pill className="h-4 w-4 text-blue-600 mb-1" />
                <span className="text-xl font-bold text-blue-700">{members_with_medications}</span>
                <span className="text-[11px] text-muted-foreground font-medium">Members</span>
              </div>
              <div className="flex flex-col items-center rounded-xl bg-amber-500/10 border border-amber-200/50 px-2 py-2.5">
                <AlertTriangle className="h-4 w-4 text-amber-600 mb-1" />
                <span className="text-xl font-bold text-amber-700">{refill_reminders.length}</span>
                <span className="text-[11px] text-muted-foreground font-medium">Refills</span>
              </div>
            </div>

            {/* Top refill reminders */}
            {topRefills.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Refill Reminders
                </p>
                {topRefills.map((refill, idx) => {
                  const badge = urgencyBadge(refill.days_until_empty);
                  return (
                    <div
                      key={`${refill.medicine}-${refill.member_name}-${idx}`}
                      className="flex items-center justify-between rounded-xl bg-muted/30 border px-3 py-2"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold truncate">{refill.medicine}</p>
                        <p className="text-xs text-muted-foreground">{refill.member_name}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        <span className="text-sm text-muted-foreground font-medium tabular-nums">
                          {refill.days_until_empty}d
                        </span>
                        <Badge className={`text-[11px] font-bold px-2 py-0.5 ${badge.cls}`}>
                          {badge.label}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
