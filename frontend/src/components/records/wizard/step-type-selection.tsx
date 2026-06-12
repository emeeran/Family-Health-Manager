import { memo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RECORD_TYPE_OPTIONS } from "@/components/records/record-form-utils";
import type { RecordType } from "@/lib/types/enums";

interface StepTypeSelectionProps {
  recordType: RecordType | undefined;
  onRecordTypeChange: (type: RecordType) => void;
  register: any;
  errors: Record<string, { message?: string }>;
  uploadSection?: React.ReactNode;
}

export const StepTypeSelection = memo(function StepTypeSelection({
  recordType,
  onRecordTypeChange,
  register,
  errors,
  uploadSection,
}: StepTypeSelectionProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Record Type & Date
        </p>
        <div className="grid gap-2 md:grid-cols-2">
          <div className="space-y-0.5">
            <Label className="text-xs">Record Type</Label>
            <input type="hidden" name="record_type" value={recordType ?? ""} />
            <Select
              value={recordType ?? ""}
              onValueChange={(v) => {
                if (v) onRecordTypeChange(v as RecordType);
              }}
            >
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                {RECORD_TYPE_OPTIONS.map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.record_type && (
              <p role="alert" className="text-[11px] text-destructive">
                {errors.record_type.message}
              </p>
            )}
          </div>
          <div className="space-y-0.5">
            <Label htmlFor="record_date" className="text-xs">
              Date
            </Label>
            <Input
              id="record_date"
              type="text"
              placeholder="DD-MM-YYYY"
              aria-describedby="err-record_date"
              {...register("record_date")}
              className="h-8"
            />
            {errors.record_date && (
              <p role="alert" className="text-[11px] text-destructive">
                {errors.record_date.message}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Upload & Extract section injected from wizard parent */}
      {uploadSection}
    </div>
  );
});
