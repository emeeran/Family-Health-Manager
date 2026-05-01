import { Badge } from "@/components/ui/badge";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";
import { cn } from "@/lib/utils";

const typeStyles: Record<RecordType, string> = {
  doctor_visit: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  lab_report: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
  rx_eyeglass: "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/20",
  blood_glucose: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  hba1c: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
  misc_record: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
  vitals: "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20",
  parkinsons_log: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
};

interface RecordTypeBadgeProps {
  type: RecordType;
  className?: string;
}

export function RecordTypeBadge({ type, className }: RecordTypeBadgeProps) {
  return (
    <Badge variant="outline" className={cn("font-medium", typeStyles[type], className)}>
      {RECORD_TYPE_LABELS[type]}
    </Badge>
  );
}
