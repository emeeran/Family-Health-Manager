import type { ReactNode } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VerificationBadge } from "@/components/shared/verification-badge";
import type { VerificationResult } from "@/lib/types/message";

function formatDate(iso?: string | null): string {
  if (!iso) return "";
  const dt = new Date(iso);
  return Number.isNaN(dt.getTime())
    ? iso
    : dt.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Shared dense-pro chrome for both report viewers: a slim sticky command bar
 * and a compact header band. Padding and type are tuned for high information
 * density while staying PDF-safe (everything stays in the document flow).
 */
export function ReportShell({
  title,
  memberName,
  subtitle,
  generatedAt,
  provider,
  reportId,
  verification,
  onBack,
  onExportPDF,
  maxWidth = 960,
  children,
}: {
  title: string;
  memberName?: string;
  subtitle?: ReactNode;
  generatedAt?: string | null;
  provider?: string | null;
  reportId?: string | null;
  verification?: VerificationResult | null;
  onBack: () => void;
  onExportPDF?: () => void;
  maxWidth?: number;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-sm print:hidden">
        <div
          className="mx-auto flex h-10 items-center justify-between gap-2 px-3"
          style={{ maxWidth }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={onBack}
              aria-label="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <span className="truncate text-[13px] font-semibold text-foreground">{title}</span>
            <VerificationBadge verification={verification} />
          </div>
          {onExportPDF && (
            <Button variant="outline" size="sm" className="h-7" onClick={onExportPDF}>
              <Download className="h-3.5 w-3.5" />
              PDF
            </Button>
          )}
        </div>
      </div>

      <div className="mx-auto px-3 py-3 print:py-0" style={{ maxWidth }}>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2 border-b border-border pb-2">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold leading-tight tracking-tight text-foreground">
              {memberName ?? title}
            </h1>
            {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2.5 text-[10px] text-muted-foreground">
            {generatedAt && <span>{formatDate(generatedAt)}</span>}
            {provider && <span className="font-mono">{provider}</span>}
            {reportId && <span className="font-mono opacity-70">#{reportId.slice(0, 8)}</span>}
          </div>
        </div>

        {children}

        <footer className="mt-4 border-t border-border pt-2 text-[10px] leading-relaxed text-muted-foreground">
          AI-generated for informational purposes only — not a substitute for professional medical
          advice. Always confirm findings and recommendations with your clinician.
        </footer>
      </div>
    </div>
  );
}
