import { memo, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { TranscriptionReportView } from "@/components/records/transcription-report-view";
import { extractReason, extractSummary } from "@/lib/record-utils";
import { formatDate } from "@/lib/utils";
import { Calendar, User, FileText } from "lucide-react";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface RecordCardProps {
  record: HealthRecordResponse;
  memberName?: string;
  member?: FamilyMemberResponse | null;
  onClick?: (record: HealthRecordResponse) => void;
}

const RecordCard = memo(function RecordCard({
  record,
  memberName,
  member,
  onClick,
}: RecordCardProps) {
  const reason = extractReason(record);
  const summaryLine = extractSummary(record);
  const hasReport = record.record_type === "doctor_visit" || record.record_type === "lab_report";

  return (
    <Card
      className="group hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
      onClick={() => onClick?.(record)}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <RecordTypeBadge type={record.record_type} />
          <div className="flex items-center gap-2">
            {hasReport && (
              <Popover modal={false}>
                <PopoverTrigger
                  openOnHover
                  delay={300}
                  closeDelay={200}
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:text-blue-500 hover:bg-blue-50 transition-colors cursor-pointer"
                  aria-label="Preview transcription report"
                >
                  <FileText className="h-3.5 w-3.5" />
                </PopoverTrigger>
                <PopoverContent
                  side="top"
                  sideOffset={8}
                  className="w-[28rem] max-h-[420px] overflow-y-auto p-0"
                >
                  <div className="p-3 space-y-2">
                    <PopoverHeader>
                      <PopoverTitle className="text-xs flex items-center gap-2">
                        <RecordTypeBadge type={record.record_type} />
                        {formatDate(record.record_date)}
                        {record.provider_name && (
                          <span className="text-muted-foreground font-normal">
                            · {record.provider_name}
                          </span>
                        )}
                      </PopoverTitle>
                    </PopoverHeader>
                    <TranscriptionReportView record={record} member={member} compact />
                    <PopoverDescription className="text-[10px] pt-1 border-t">
                      Click card to view full record
                    </PopoverDescription>
                  </div>
                </PopoverContent>
              </Popover>
            )}
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDate(record.record_date)}
            </span>
          </div>
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
          {memberName !== undefined && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <User className="h-3 w-3" />
              {memberName || "—"}
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
});

interface RecordsCardsProps {
  records: HealthRecordResponse[];
  memberNames?: Record<string, string>;
  membersById?: Record<string, FamilyMemberResponse>;
  onCardClick?: (record: HealthRecordResponse) => void;
}

export function RecordsCards({
  records,
  memberNames,
  membersById,
  onCardClick,
}: RecordsCardsProps) {
  const handleClick = useCallback(
    (record: HealthRecordResponse) => onCardClick?.(record),
    [onCardClick]
  );

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {records.map((record) => (
        <RecordCard
          key={record.id}
          record={record}
          memberName={memberNames?.[record.family_member_id]}
          member={membersById?.[record.family_member_id]}
          onClick={handleClick}
        />
      ))}
    </div>
  );
}
