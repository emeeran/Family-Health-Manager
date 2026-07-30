/**
 * Shared report footer: composes the print-safe {@link ValidationFootnote} with
 * a freshness line ("Records as of …") and an expandable source-records list
 * (themes 1 & 3). Always-visible, fixed-light-gray DOM so it renders identically
 * on screen, in `window.print()`, and in `exportElementToPDF` captures.
 */

import { useState } from "react";
import { FileText, ChevronDown, ChevronRight } from "lucide-react";
import { ValidationFootnote } from "@/components/members/reports/validation-footnote";
import type { ReportMeta, SourceRef } from "@/lib/types/report-meta";
import type { VerificationResult } from "@/lib/types/message";

function fmtDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}

export function ReportFooter({
  provider,
  verification,
  generatedAt,
  note,
  meta,
}: {
  provider?: string | null;
  verification?: VerificationResult | null;
  generatedAt?: string;
  note?: string;
  meta?: ReportMeta | null;
}) {
  const [open, setOpen] = useState(false);
  const sources = meta?.sources ?? [];
  const freshness = fmtDate(meta?.freshness_as_of);
  const rangeStart = fmtDate(meta?.range_start);
  const hasSources = sources.length > 0;

  return (
    <div className="space-y-2 break-inside-avoid">
      <ValidationFootnote
        provider={provider}
        verification={verification}
        generatedAt={generatedAt}
        note={note}
      />
      {(freshness || hasSources) && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-[11px] leading-relaxed text-gray-600">
          {freshness && (
            <div className="flex flex-wrap items-center gap-x-1.5">
              <span className="font-semibold text-gray-700">Records as of {freshness}</span>
              {rangeStart && rangeStart !== freshness && (
                <span className="text-gray-400">
                  {" "}
                  ({rangeStart} – {freshness}, {sources.length} record
                  {sources.length > 1 ? "s" : ""})
                </span>
              )}
              {!rangeStart && hasSources && (
                <span className="text-gray-400">
                  {" "}
                  · {sources.length} source record{sources.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
          )}
          {hasSources && (
            <div className="mt-1">
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-gray-500 hover:text-gray-700 hover:underline"
              >
                {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                {open ? "Hide" : "Show"} source records
              </button>
              {open && (
                <ul className="mt-1.5 space-y-1">
                  {sources.map((s: SourceRef) => (
                    <li key={s.id} className="flex gap-1.5">
                      <FileText className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
                      <span>
                        {s.date && <span className="text-gray-500">{fmtDate(s.date)}</span>}
                        {s.type && <span className="text-gray-400"> · {s.type}</span>}
                        {s.summary && <span className="text-gray-600"> — {s.summary}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
