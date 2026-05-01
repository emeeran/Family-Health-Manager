"use client";

import { getTables } from "@/lib/record-type-configs";
import type { RecordTypeConfig } from "@/lib/record-type-configs";
import type { ExtractionBatch } from "@/lib/extraction-store";
import { CustomFieldRenderer } from "./custom-field-renderer";
import { DynamicTable } from "./dynamic-table";

interface TypeSpecificFieldsProps {
  config: RecordTypeConfig;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  tableData: Record<string, Record<string, string>[]>;
  onTableChange: (tableKey: string, rows: Record<string, string>[]) => void;
  onAutoFillBatch?: (tableKey: string, batchId: string) => void;
  autoFillBatches?: ExtractionBatch[];
  errors?: Record<string, string>;
}

export function TypeSpecificFields({
  config,
  values,
  onChange,
  tableData,
  onTableChange,
  onAutoFillBatch,
  autoFillBatches,
  errors,
}: TypeSpecificFieldsProps) {
  const hasCustomFields = config.customFields.length > 0;
  const tables = getTables(config);
  const hasTables = tables.length > 0;

  if (!hasCustomFields && !hasTables) return null;

  return (
    <div className="space-y-2.5">
      {config.description && <p className="text-xs text-muted-foreground">{config.description}</p>}
      {hasCustomFields && (
        <div className="grid gap-2 md:grid-cols-2">
          {config.customFields.map((field) => (
            <CustomFieldRenderer
              key={field.key}
              field={field}
              value={values[field.key] || ""}
              onChange={onChange}
              error={errors?.[field.key]}
              className={field.span === 2 ? "md:col-span-2" : undefined}
            />
          ))}
        </div>
      )}
      {hasTables &&
        tables.map((tableDef) => {
          // Determine auto-fill data type based on table key
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
    </div>
  );
}
