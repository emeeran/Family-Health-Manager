import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { WandSparkles, FileText, ChevronRight } from "lucide-react";
import type { ExtractionBatch } from "@/lib/extraction-store";

interface AutoFillPickerProps {
  batches: ExtractionBatch[];
  dataType: "prescriptions" | "labTests" | "eyeglass";
  onSelect: (batchId: string) => void;
  disabled?: boolean;
}

function batchSummary(
  batch: ExtractionBatch,
  dataType: "prescriptions" | "labTests" | "eyeglass"
): string {
  if (dataType === "prescriptions") {
    const count = batch.prescriptions.length;
    if (count === 0) return "";
    const names = batch.prescriptions
      .slice(0, 2)
      .map((p) => p.medicine || "Unknown")
      .join(", ");
    return count <= 2 ? names : `${names} +${count - 2} more`;
  }
  if (dataType === "labTests") {
    const count = batch.labTests.length;
    if (count === 0) return "";
    const names = batch.labTests
      .slice(0, 2)
      .map((t) => t.test_name || "Test")
      .join(", ");
    return count <= 2 ? names : `${names} +${count - 2} more`;
  }
  if (dataType === "eyeglass" && batch.eyeglass) {
    return "RE/LE prescription data";
  }
  return "";
}

function timeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function AutoFillPicker({ batches, dataType, onSelect, disabled }: AutoFillPickerProps) {
  if (batches.length === 0) {
    return (
      <Button type="button" variant="outline" size="sm" disabled>
        <WandSparkles className="h-3 w-3 mr-1" />
        No data
      </Button>
    );
  }

  if (batches.length === 1) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        className="border-green-300 bg-green-50 text-green-700 hover:bg-green-100 dark:border-green-700 dark:bg-green-950 dark:text-green-400 dark:hover:bg-green-900"
        onClick={() => onSelect(batches[0].id)}
      >
        <WandSparkles className="h-3 w-3 mr-1" />
        Auto-fill
      </Button>
    );
  }

  return (
    <Popover>
      <PopoverTrigger
        className="inline-flex items-center justify-center gap-1 whitespace-nowrap rounded-md text-sm font-medium transition-colors border border-green-300 bg-green-50 text-green-700 hover:bg-green-100 h-8 px-3 dark:border-green-700 dark:bg-green-950 dark:text-green-400 dark:hover:bg-green-900 disabled:pointer-events-none disabled:opacity-50"
        disabled={disabled}
      >
        <WandSparkles className="h-3 w-3" />
        Auto-fill
        <span className="ml-0.5 rounded-full bg-green-200 px-1.5 text-[10px] font-bold leading-none dark:bg-green-800">
          {batches.length}
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-1.5">
        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
          Select extraction to apply
        </div>
        <div className="space-y-0.5">
          {batches.map((batch) => {
            const summary = batchSummary(batch, dataType);
            if (!summary) return null;
            return (
              <button
                key={batch.id}
                type="button"
                className="w-full flex items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-accent transition-colors group"
                onClick={() => onSelect(batch.id)}
              >
                <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-sm font-medium truncate">{batch.fileName}</span>
                    <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                      {timeAgo(batch.timestamp)}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground truncate block">{summary}</span>
                </div>
                <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
