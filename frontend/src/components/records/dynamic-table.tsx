import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, ClipboardPaste } from "lucide-react";
import { AutoFillPicker } from "./auto-fill-picker";
import type { ExtractionBatch } from "@/lib/extraction-store";
import type { TableRowDef } from "@/lib/record-type-configs";

/**
 * Parse pasted tabular text into rows matching the table's field order.
 * Splits each line on tab / comma / pipe / 2+ spaces and maps columns onto
 * def.fields in order. Lines whose first (primary) column is empty are dropped.
 */
export function parsePastedRows(text: string, fields: { key: string }[]): Record<string, string>[] {
  const out: Record<string, string>[] = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const cols = line
      .split(/\t|\s*\|\s*|\s{2,}|,/)
      .map((c) => c.trim())
      .filter((c) => c.length);
    if (cols.length === 0 || !cols[0]) continue;
    const row: Record<string, string> = {};
    fields.forEach((f, i) => {
      row[f.key] = cols[i] ?? "";
    });
    out.push(row);
  }
  return out;
}

interface DynamicTableProps {
  def: TableRowDef;
  rows: Record<string, string>[];
  onChange: (rows: Record<string, string>[]) => void;
  onAutoFillBatch?: (batchId: string) => void;
  autoFillBatches?: ExtractionBatch[];
  autoFillDataType?: "prescriptions" | "labTests" | "eyeglass";
  /** Per-field autocomplete suggestions, keyed by field key (e.g. { medicine: [...] }). */
  suggestions?: Record<string, string[]>;
}

function emptyRow(fields: { key: string }[]): Record<string, string> {
  const row: Record<string, string> = {};
  for (const f of fields) row[f.key] = "";
  return row;
}

export function DynamicTable({
  def,
  rows,
  onChange,
  onAutoFillBatch,
  autoFillBatches,
  autoFillDataType,
  suggestions,
}: DynamicTableProps) {
  function updateRow(index: number, key: string, value: string) {
    const updated = rows.map((row, i) => (i === index ? { ...row, [key]: value } : row));
    onChange(updated);
  }

  function addRow() {
    onChange([...rows, emptyRow(def.fields)]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");

  function applyPaste() {
    const parsed = parsePastedRows(pasteText, def.fields);
    if (parsed.length > 0) onChange([...rows, ...parsed]);
    setPasteText("");
    setShowPaste(false);
  }

  const hasBatches = autoFillBatches && autoFillBatches.length > 0;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium">{def.label}</Label>
        <div className="flex gap-2">
          {onAutoFillBatch && autoFillDataType && (
            <AutoFillPicker
              batches={autoFillBatches || []}
              dataType={autoFillDataType}
              onSelect={onAutoFillBatch}
            />
          )}
          {def.allowAddRemove && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowPaste(true)}
                title={`Paste ${def.label.toLowerCase()} as a table`}
              >
                <ClipboardPaste className="h-3 w-3 mr-1" /> Paste
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={addRow}>
                <Plus className="h-3 w-3 mr-1" /> Add Row
              </Button>
            </>
          )}
        </div>
      </div>

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                {def.fields.map((field) => (
                  <th
                    key={field.key}
                    className="py-1.5 px-1 text-left text-xs text-muted-foreground font-medium whitespace-nowrap"
                  >
                    {field.label}
                  </th>
                ))}
                {def.allowAddRemove && <th className="py-1.5 px-1 w-8"></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => (
                <tr key={rowIdx} className="border-b border-border/50">
                  {def.fields.map((field) => {
                    const fieldSuggestions = suggestions?.[field.key];
                    const listId =
                      fieldSuggestions && fieldSuggestions.length > 0
                        ? `dt-${def.key}-${field.key}`
                        : undefined;
                    return (
                      <td key={field.key} className="py-1 px-0.5">
                        {field.type === "select" ? (
                          <Select
                            value={row[field.key] || ""}
                            onValueChange={(v) => updateRow(rowIdx, field.key, v ?? "")}
                          >
                            <SelectTrigger className="h-7 text-xs min-w-[80px]">
                              <SelectValue placeholder={field.placeholder || field.label} />
                            </SelectTrigger>
                            <SelectContent>
                              {field.options?.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>
                                  {opt.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            type={field.type === "number" ? "number" : "text"}
                            value={row[field.key] || ""}
                            onChange={(e) => updateRow(rowIdx, field.key, e.target.value)}
                            placeholder={field.placeholder}
                            className="h-7 text-xs min-w-[60px]"
                            step={field.step}
                            min={field.min}
                            max={field.max}
                            list={listId}
                          />
                        )}
                      </td>
                    );
                  })}
                  {def.allowAddRemove && (
                    <td className="py-1 px-0.5">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={() => removeRow(rowIdx)}
                      >
                        <Trash2 className="h-3 w-3 text-muted-foreground" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-2.5 text-sm text-muted-foreground border rounded-md">
          {hasBatches
            ? 'Extraction data ready — click "Auto-fill" to select and populate.'
            : "No rows added yet."}
        </div>
      )}

      {/* Autocomplete suggestion lists (one per suggested field, referenced by input `list`) */}
      {def.fields.map((field) => {
        const opts = suggestions?.[field.key];
        if (!opts || opts.length === 0) return null;
        return (
          <datalist key={`dl-${def.key}-${field.key}`} id={`dt-${def.key}-${field.key}`}>
            {opts.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        );
      })}

      {/* Paste-rows dialog — bulk import from pasted tab/CSV text */}
      <Dialog open={showPaste} onOpenChange={setShowPaste}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Paste {def.label}</DialogTitle>
            <DialogDescription>
              One row per line. Columns are mapped in order:{" "}
              {def.fields.map((f) => f.label).join(" · ")}. Separate columns with tab, comma, pipe,
              or 2+ spaces.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={6}
            placeholder={def.fields.map((f) => f.placeholder || f.label).join("\t")}
            className="text-xs font-mono"
          />
          <DialogFooter>
            <Button type="button" variant="outline" size="sm" onClick={() => setShowPaste(false)}>
              Cancel
            </Button>
            <Button type="button" size="sm" onClick={applyPaste} disabled={!pasteText.trim()}>
              Add Rows
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
