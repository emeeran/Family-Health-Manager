import { useState, useMemo, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Plus, RefreshCw, Minus, Loader2, Pill, AlertTriangle } from "lucide-react";
import type { MedicationDiffItem, MedicationDiffResponse } from "@/lib/types/health-record";

interface MedicationSyncDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  diff: MedicationDiffResponse;
  onApply: (
    apply_added: string[],
    apply_updated: string[],
    apply_removed: string[]
  ) => Promise<void>;
}

type ChangeType = "added" | "updated" | "removed";

interface SelectionItem {
  medicine: string;
  type: ChangeType;
  data: MedicationDiffItem;
  selected: boolean;
}

function ChangeRow({
  item,
  changeType,
  checked,
  onCheckedChange,
}: {
  item: MedicationDiffItem;
  changeType: ChangeType;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const colorMap: Record<ChangeType, string> = {
    added: "border-emerald-200 bg-emerald-50/50",
    updated: "border-amber-200 bg-amber-50/50",
    removed: "border-red-200 bg-red-50/50",
  };

  const iconMap: Record<ChangeType, typeof Plus> = {
    added: Plus,
    updated: RefreshCw,
    removed: Minus,
  };

  const badgeVariantMap: Record<ChangeType, string> = {
    added: "bg-emerald-100 text-emerald-700",
    updated: "bg-amber-100 text-amber-700",
    removed: "bg-red-100 text-red-700",
  };

  const Icon = iconMap[changeType];

  return (
    <div className={`flex items-start gap-3 rounded-lg border p-3 ${colorMap[changeType]}`}>
      <Checkbox
        checked={checked}
        onCheckedChange={(v) => onCheckedChange(!!v)}
        className="mt-0.5"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{item.medicine}</span>
          {item.type && (
            <Badge variant="secondary" className="text-[10px] px-1.5">
              {item.type}
            </Badge>
          )}
          <Badge
            variant="secondary"
            className={`text-[10px] px-1.5 ${badgeVariantMap[changeType]}`}
          >
            <Icon className="h-3 w-3 mr-0.5" />
            {changeType}
          </Badge>
        </div>

        {changeType === "added" && (
          <p className="text-xs text-muted-foreground mt-1">
            {item.new_dosage && `${item.new_dosage}`}
            {item.new_timing && ` · ${item.new_timing.replace(/_/g, " ")}`}
            {item.new_duration && ` · ${item.new_duration}`}
          </p>
        )}

        {changeType === "updated" && (
          <div className="text-xs text-muted-foreground mt-1 space-y-0.5">
            {item.old_dosage !== item.new_dosage && (
              <p>
                Dosage: <span className="line-through">{item.old_dosage}</span>{" "}
                <span className="text-amber-700 font-medium">{item.new_dosage}</span>
              </p>
            )}
            {item.old_timing !== item.new_timing && (
              <p>
                Timing: <span className="line-through">{item.old_timing?.replace(/_/g, " ")}</span>{" "}
                <span className="text-amber-700 font-medium">
                  {item.new_timing?.replace(/_/g, " ")}
                </span>
              </p>
            )}
            {item.old_duration !== item.new_duration && (
              <p>
                Duration: <span className="line-through">{item.old_duration}</span>{" "}
                <span className="text-amber-700 font-medium">{item.new_duration}</span>
              </p>
            )}
          </div>
        )}

        {changeType === "removed" && (
          <p className="text-xs text-muted-foreground mt-1">
            {item.old_dosage && `${item.old_dosage}`}
            {item.old_timing && ` · ${item.old_timing.replace(/_/g, " ")}`}
            {item.old_duration && ` · ${item.old_duration}`}
          </p>
        )}
      </div>
    </div>
  );
}

export function MedicationSyncDialog({
  open,
  onOpenChange,
  diff,
  onApply,
}: MedicationSyncDialogProps) {
  const [selections, setSelections] = useState<Record<string, boolean>>(() => {
    // Default: select all items
    const sel: Record<string, boolean> = {};
    for (const item of diff.added) sel[`added:${item.medicine}`] = true;
    for (const item of diff.updated) sel[`updated:${item.medicine}`] = true;
    // Default: do NOT auto-select removed items (safer)
    for (const item of diff.removed) sel[`removed:${item.medicine}`] = false;
    return sel;
  });

  // Reset selections when diff changes (e.g., dialog reused for a different record)
  useEffect(() => {
    const sel: Record<string, boolean> = {};
    for (const item of diff.added) sel[`added:${item.medicine}`] = true;
    for (const item of diff.updated) sel[`updated:${item.medicine}`] = true;
    for (const item of diff.removed) sel[`removed:${item.medicine}`] = false;
    setSelections(sel);
  }, [diff]);

  const [applying, setApplying] = useState(false);

  const hasChanges = diff.added.length + diff.updated.length + diff.removed.length > 0;

  const allItems = useMemo(() => {
    const items: SelectionItem[] = [];
    for (const item of diff.added) {
      items.push({
        medicine: item.medicine,
        type: "added",
        data: item,
        selected: selections[`added:${item.medicine}`] ?? true,
      });
    }
    for (const item of diff.updated) {
      items.push({
        medicine: item.medicine,
        type: "updated",
        data: item,
        selected: selections[`updated:${item.medicine}`] ?? true,
      });
    }
    for (const item of diff.removed) {
      items.push({
        medicine: item.medicine,
        type: "removed",
        data: item,
        selected: selections[`removed:${item.medicine}`] ?? false,
      });
    }
    return items;
  }, [diff, selections]);

  function toggleSelection(key: string, checked: boolean) {
    setSelections((prev) => ({ ...prev, [key]: checked }));
  }

  async function handleApply() {
    const applyAdded: string[] = [];
    const applyUpdated: string[] = [];
    const applyRemoved: string[] = [];

    for (const item of allItems) {
      if (!item.selected) continue;
      if (item.type === "added") applyAdded.push(item.medicine);
      else if (item.type === "updated") applyUpdated.push(item.medicine);
      else if (item.type === "removed") applyRemoved.push(item.medicine);
    }

    if (applyAdded.length + applyUpdated.length + applyRemoved.length === 0) {
      onOpenChange(false);
      return;
    }

    setApplying(true);
    try {
      await onApply(applyAdded, applyUpdated, applyRemoved);
      onOpenChange(false);
    } finally {
      setApplying(false);
    }
  }

  if (!hasChanges) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pill className="h-5 w-5 text-teal-600" />
            Medication Changes Detected
          </DialogTitle>
          <DialogDescription>
            Review the changes from this prescription against your current medications. Confirm
            which changes to apply.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {diff.removed.length > 0 && (
            <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-md p-2">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>
                {diff.removed.length} medication{diff.removed.length !== 1 ? "s" : ""} from your
                active list {diff.removed.length !== 1 ? "are" : "is"} not in this prescription.
                Select carefully before removing.
              </span>
            </div>
          )}

          {allItems.map((item) => (
            <ChangeRow
              key={`${item.type}:${item.medicine}`}
              item={item.data}
              changeType={item.type}
              checked={selections[`${item.type}:${item.medicine}`] ?? false}
              onCheckedChange={(checked) =>
                toggleSelection(`${item.type}:${item.medicine}`, checked)
              }
            />
          ))}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Skip
          </Button>
          <Button
            onClick={handleApply}
            disabled={applying}
            className="bg-teal-600 hover:bg-teal-700 text-white"
          >
            {applying ? (
              <>
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                Applying...
              </>
            ) : (
              <>Apply Changes ({allItems.filter((i) => i.selected).length} selected)</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
