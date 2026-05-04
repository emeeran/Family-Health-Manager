import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { exportRecords, exportMedications, exportLabResults } from "@/lib/api/export";
import { toast } from "sonner";

interface ExportButtonProps {
  memberId?: string;
  variant?: "outline" | "ghost" | "secondary";
  size?: "sm" | "default" | "icon";
}

export function ExportButton({ memberId, variant = "outline", size = "sm" }: ExportButtonProps) {
  const [loading, setLoading] = useState(false);

  async function handleExport(fn: () => Promise<void>, label: string) {
    setLoading(true);
    try {
      await fn();
      toast.success(`${label} exported successfully`);
    } catch {
      toast.error(`Failed to export ${label.toLowerCase()}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger>
        <Button variant={variant} size={size} disabled={loading}>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          <span className="ml-1.5 hidden sm:inline">Export</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => handleExport(() => exportRecords(memberId), "Records")}>
          Health Records
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => handleExport(() => exportMedications(memberId), "Medications")}
        >
          Medications
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => handleExport(() => exportLabResults(memberId), "Lab Results")}
        >
          Lab Results
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
