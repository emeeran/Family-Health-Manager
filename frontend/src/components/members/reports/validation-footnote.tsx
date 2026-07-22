/**
 * Print-safe provenance + validation footnote for AI-generated reports.
 *
 * Renders INLINE (no popover) so it is captured by `exportElementToPDF`
 * (html2canvas renders the live DOM) and by `window.print()`. Unlike
 * {@link VerificationBadge} it is ALWAYS visible — including failed /
 * unverifiable / not-yet-validated states — so anything printed is clearly
 * marked as AI-generated and shows its validation state. Uses fixed-light
 * gray classes to match the "document page" look of the report viewers.
 */

import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Loader2,
  XCircle,
  ShieldCheck,
  AlertCircle,
  Cpu,
} from "lucide-react";
import type { VerificationResult } from "@/lib/types/message";

type StatusCfg = { Icon: typeof CheckCircle2; label: string; tone: string };

const STATUS: Record<string, StatusCfg> = {
  verified: { Icon: CheckCircle2, label: "Verified", tone: "text-emerald-600" },
  auto_verified: { Icon: ShieldCheck, label: "Auto-verified", tone: "text-sky-600" },
  warnings: { Icon: AlertTriangle, label: "Verified — with warnings", tone: "text-amber-600" },
  unverifiable: { Icon: HelpCircle, label: "Could not verify", tone: "text-gray-500" },
  pending: { Icon: Loader2, label: "Validation in progress", tone: "text-gray-500" },
  failed: { Icon: XCircle, label: "Validation failed", tone: "text-gray-500" },
};

function statusConfig(verification?: VerificationResult | null): StatusCfg {
  if (!verification) {
    return { Icon: AlertCircle, label: "Not validated", tone: "text-gray-500" };
  }
  return (
    STATUS[verification.status] ?? {
      Icon: AlertCircle,
      label: verification.status.replace(/_/g, " "),
      tone: "text-gray-500",
    }
  );
}

export function ValidationFootnote({
  provider,
  verification,
  generatedAt,
  note,
}: {
  /** The AI provider/model used to generate the report (``provider_used``). */
  provider?: string | null;
  verification?: VerificationResult | null;
  generatedAt?: string;
  note?: string;
}) {
  const { Icon } = statusConfig(verification);
  const claims = verification?.claims_checked;
  const verifier = verification?.verifier_provider;
  const highWarnings = (verification?.warnings ?? []).filter((w) => w?.severity === "high");
  const isPending = verification?.status === "pending";

  return (
    <div className="break-inside-avoid rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-[11px] leading-relaxed text-gray-600">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1 font-semibold text-gray-700">
          <Cpu className="h-3 w-3" />
          AI-generated{provider ? ` · ${provider}` : ""}
        </span>
        <span className="text-gray-300">|</span>
        <span
          className={`inline-flex items-center gap-1 font-medium ${statusConfig(verification).tone}`}
        >
          <Icon className={`h-3 w-3 ${isPending ? "animate-spin" : ""}`} />
          {statusConfig(verification).label}
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-gray-500">
        {typeof claims === "number" && claims > 0 && (
          <span>
            {claims} claim{claims > 1 ? "s" : ""} checked{verifier ? ` via ${verifier}` : ""}
          </span>
        )}
        {highWarnings.length > 0 && (
          <>
            {typeof claims === "number" && claims > 0 && <span className="text-gray-300">·</span>}
            <span className="font-medium text-red-600">
              {highWarnings.length} high-severity warning{highWarnings.length > 1 ? "s" : ""}
            </span>
          </>
        )}
        {generatedAt && (
          <>
            {(typeof claims === "number" && claims > 0) || highWarnings.length > 0 ? (
              <span className="text-gray-300">·</span>
            ) : null}
            <span>Generated {new Date(generatedAt).toLocaleDateString()}</span>
          </>
        )}
      </div>

      <p className="mt-1.5 text-gray-500">
        {note ??
          "AI-generated for educational purposes. Verify with a licensed clinician before acting on it."}
      </p>
    </div>
  );
}
