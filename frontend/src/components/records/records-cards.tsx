import { Card, CardContent } from "@/components/ui/card";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { extractReason, extractSummary } from "@/lib/record-utils";
import { formatDate } from "@/lib/utils";
import { Calendar, User } from "lucide-react";
import type { HealthRecordResponse } from "@/lib/types/health-record";

interface RecordsCardsProps {
  records: HealthRecordResponse[];
  memberNames?: Record<string, string>;
  onCardClick?: (record: HealthRecordResponse) => void;
}

export function RecordsCards({ records, memberNames, onCardClick }: RecordsCardsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {records.map((record) => {
        const reason = extractReason(record);
        const summaryLine = extractSummary(record);
        return (
          <Card
            key={record.id}
            className="group hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
            onClick={() => onCardClick?.(record)}
          >
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <RecordTypeBadge type={record.record_type} />
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  {formatDate(record.record_date)}
                </span>
              </div>

              {reason ? (
                <p className="text-sm font-medium leading-snug line-clamp-2">{reason}</p>
              ) : (
                <p className="text-sm text-muted-foreground">No diagnosis recorded</p>
              )}

              {summaryLine && (
                <p className="text-xs text-muted-foreground/70 line-clamp-1">{summaryLine}</p>
              )}

              <div className="flex items-center justify-between pt-1">
                {memberNames && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {memberNames[record.family_member_id] || "—"}
                  </span>
                )}
                {record.provider_name && (
                  <span className="text-xs text-muted-foreground truncate max-w-[140px]">
                    {record.provider_name}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
