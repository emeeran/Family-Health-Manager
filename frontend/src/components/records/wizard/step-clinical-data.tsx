import { memo, useMemo } from "react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TypeSpecificFields } from "@/components/records/type-specific-fields";
import { DynamicTable } from "@/components/records/dynamic-table";
import { getConfig, getTables } from "@/lib/record-type-configs";
import type { ExtractionBatch } from "@/lib/extraction-store";
import type { RecordType } from "@/lib/types/enums";
import type { RecordTypeConfig } from "@/lib/record-type-configs";

interface StepClinicalDataProps {
  recordType: RecordType | undefined;
  config: RecordTypeConfig | null;
  customValues: Record<string, string>;
  onCustomFieldChange: (key: string, value: string) => void;
  tableData: Record<string, Record<string, string>[]>;
  onTableChange: (tableKey: string, rows: Record<string, string>[]) => void;
  onAutoFillBatch?: (tableKey: string, batchId: string) => void;
  autoFillBatches: ExtractionBatch[];
  notes: string;
  onNotesChange: (value: string) => void;
  isDoctorVisit: boolean;
  clinicalDataRef: React.RefObject<HTMLInputElement | null>;
  register: any;
}

export const StepClinicalData = memo(function StepClinicalData({
  recordType,
  config,
  customValues,
  onCustomFieldChange,
  tableData,
  onTableChange,
  onAutoFillBatch,
  autoFillBatches,
  notes,
  onNotesChange,
  isDoctorVisit,
  clinicalDataRef,
  register,
}: StepClinicalDataProps) {
  const tables = useMemo(() => (recordType ? getTables(getConfig(recordType)) : []), [recordType]);

  // For doctor visits, hide chief_complaint and notes from TypeSpecificFields (handled in step 2)
  const typeSpecificConfig = useMemo(() => {
    if (!config) return null;
    if (isDoctorVisit) {
      const hiddenKeys = new Set(["chief_complaint", "notes"]);
      return {
        ...config,
        customFields: config.customFields.filter((f) => !hiddenKeys.has(f.key)),
        tables: undefined,
        tableRows: undefined,
      };
    }
    return config;
  }, [config, isDoctorVisit]);

  const hasCustomFields = config && config.customFields.length > 0;
  const hasTables = tables.length > 0;
  const hasStructuredContent = hasCustomFields || hasTables;

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Clinical Data
      </p>

      {/* Type-specific fields */}
      {typeSpecificConfig && (
        <TypeSpecificFields
          config={typeSpecificConfig}
          values={customValues}
          onChange={onCustomFieldChange}
          tableData={tableData}
          onTableChange={onTableChange}
          onAutoFillBatch={onAutoFillBatch}
          autoFillBatches={autoFillBatches}
        />
      )}

      {/* Doctor visit prescription & lab tables */}
      {isDoctorVisit &&
        tables.map((tableDef) => {
          const autoFillDataType =
            tableDef.key === "prescriptions"
              ? ("prescriptions" as const)
              : tableDef.key === "tests" || tableDef.key === "lab_results"
                ? ("labTests" as const)
                : undefined;
          return (
            <DynamicTable
              key={tableDef.key}
              def={tableDef}
              rows={tableData[tableDef.key] || []}
              onChange={(rows) => onTableChange(tableDef.key, rows)}
              onAutoFillBatch={
                onAutoFillBatch
                  ? (batchId: string) => onAutoFillBatch(tableDef.key, batchId)
                  : undefined
              }
              autoFillBatches={autoFillBatches}
              autoFillDataType={autoFillDataType}
            />
          );
        })}

      {/* Notes for non-doctor-visit structured types */}
      {hasStructuredContent && !isDoctorVisit && (
        <div className="space-y-0.5">
          <Label htmlFor="additional_notes" className="text-xs">
            Notes (optional)
          </Label>
          <Textarea
            id="additional_notes"
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
            rows={1}
            placeholder="Any additional notes..."
            className="text-sm"
          />
        </div>
      )}

      {/* Clinical data fallback for types without structured content */}
      {!hasStructuredContent && (
        <div className="space-y-0.5">
          <Label htmlFor="clinical_data" className="text-xs">
            Clinical Data
          </Label>
          <Textarea
            id="clinical_data"
            {...register("clinical_data")}
            rows={3}
            placeholder="Enter clinical data, observations, notes..."
            className="text-sm"
            onChange={(e) => {
              if (clinicalDataRef.current) clinicalDataRef.current.value = e.target.value;
              register("clinical_data").onChange(e);
            }}
          />
        </div>
      )}
    </div>
  );
});
