import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadHealthSummary } from "@/lib/api/reports";
import { toast } from "sonner";

interface ReportGeneratorProps {
  memberId?: string;
  variant?: "outline" | "ghost" | "secondary";
}

export function ReportGenerator({ memberId, variant = "outline" }: ReportGeneratorProps) {
  const [loading, setLoading] = useState(false);

  async function handleGenerate() {
    setLoading(true);
    try {
      await downloadHealthSummary(memberId);
      toast.success("Health summary downloaded");
    } catch {
      toast.error("Failed to generate report");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button variant={variant} size="sm" onClick={handleGenerate} disabled={loading}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
      <span className="ml-1.5">Health Summary</span>
    </Button>
  );
}
