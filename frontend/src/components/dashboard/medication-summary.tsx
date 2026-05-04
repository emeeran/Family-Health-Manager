import { Pill, AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { MedicationSummary } from "@/lib/types/dashboard";

interface MedicationSummaryWidgetProps {
  summary: MedicationSummary;
  memberNames: Record<string, string>;
}

function urgencyCls(days: number): string {
  if (days <= 3) return "text-red-700 bg-red-100 border-red-200";
  if (days <= 7) return "text-amber-700 bg-amber-100 border-amber-200";
  return "text-emerald-700 bg-emerald-100 border-emerald-200";
}

export function MedicationSummaryWidget({ summary }: MedicationSummaryWidgetProps) {
  const { total_active_medications, members_with_medications, refill_reminders } = summary;
  const topRefills = refill_reminders.slice(0, 3);

  if (total_active_medications === 0) return null;

  return (
    <Card className="shadow-sm">
      <CardContent className="pt-4 pb-3 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Pill className="h-4 w-4 text-violet-500" />
          Medications
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="text-center rounded-lg bg-muted/50 py-2">
            <p className="text-lg font-bold">{total_active_medications}</p>
            <p className="text-[10px] text-muted-foreground">Active</p>
          </div>
          <div className="text-center rounded-lg bg-muted/50 py-2">
            <p className="text-lg font-bold">{members_with_medications}</p>
            <p className="text-[10px] text-muted-foreground">Members</p>
          </div>
          <div className="text-center rounded-lg bg-muted/50 py-2">
            <p className="text-lg font-bold">{refill_reminders.length}</p>
            <p className="text-[10px] text-muted-foreground">Refills</p>
          </div>
        </div>
        {topRefills.length > 0 && (
          <div className="space-y-1.5">
            {topRefills.map((refill, idx) => (
              <div
                key={`${refill.medicine}-${idx}`}
                className="flex items-center justify-between rounded-lg bg-muted/30 px-2.5 py-1.5"
              >
                <div className="min-w-0">
                  <p className="text-xs font-semibold truncate">{refill.medicine}</p>
                  <p className="text-[10px] text-muted-foreground">{refill.member_name}</p>
                </div>
                <Badge
                  className={`text-[10px] font-bold px-1.5 py-0.5 border ${urgencyCls(refill.days_until_empty)}`}
                >
                  {refill.days_until_empty}d
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
