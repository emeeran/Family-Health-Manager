/**
 * Live, progressively-formatted preview of an AI insight as it streams.
 *
 * Replaces the old plain `whitespace-pre-wrap` text: as tokens arrive the
 * accumulating markdown is re-parsed (`parseSections`) and rendered as
 * colored section headings + inline-formatted prose, with a blinking cursor on
 * the in-flight (last) section. A stage/provider chip sits above so the user
 * can see *what* is happening, not just the raw stream. Before the first
 * heading lands, the raw stream is shown verbatim (with a cursor) so there's
 * never a blank panel. Fully additive/degrading — empty/odd text is harmless.
 */

import { memo } from "react";
import { Loader2, FileText, Cloud, Cpu } from "lucide-react";
import { parseSections } from "@/lib/parse-sections";
import { classifyStage, hasStructuredContent } from "@/lib/streaming-preview-select";
import { renderInline } from "@/components/members/reports/insight-section";
import { cn } from "@/lib/utils";

const KEY_ACCENT: Record<string, string> = {
  overview: "#5b7fff",
  conditions: "#dc2626",
  labs: "#4ade80",
  risk: "#fb923c",
  recommendations: "#06b6d4",
  follow_up: "#ec4899",
  other: "#737373",
};

const STAGE_KIND_STYLE = {
  context: { Icon: FileText, cls: "text-sky-600 bg-sky-50 ring-sky-200" },
  cloud: { Icon: Cloud, cls: "text-violet-600 bg-violet-50 ring-violet-200" },
  local: { Icon: Cpu, cls: "text-orange-600 bg-orange-50 ring-orange-200" },
} as const;

/** Split a section body into non-empty display lines (paragraphs ≈ line breaks). */
function toLines(body: string): string[] {
  return body
    .split(/\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function Cursor() {
  return (
    <span className="ml-0.5 inline-block h-3.5 w-[3px] animate-pulse rounded-sm bg-(--brand-accent) align-text-bottom" />
  );
}

export const StreamingPreview = memo(function StreamingPreview({
  text,
  stage,
  className,
}: {
  text: string;
  stage?: string;
  className?: string;
}) {
  const sections = parseSections(text ?? "");
  const style = stage ? STAGE_KIND_STYLE[classifyStage(stage)] : null;
  // parseSections returns a single fallback "Health Insights" section when no
  // heading has been emitted yet — in that case show the raw stream + cursor.
  const structured = hasStructuredContent(text ?? "");

  return (
    <div className={cn("space-y-2.5", className)}>
      {style && stage && (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1",
              style.cls
            )}
          >
            <style.Icon className="h-3 w-3" />
            <span className="max-w-[280px] truncate">{stage}</span>
          </span>
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        </div>
      )}

      <div className="max-h-40 overflow-y-auto rounded-lg bg-white/60 p-2.5 text-[13px] leading-snug text-gray-700 ring-1 ring-gray-100">
        {structured ? (
          <div className="space-y-2.5">
            {sections.map((section, i) => {
              const accent = KEY_ACCENT[section.key ?? "other"] ?? "#737373";
              const isLast = i === sections.length - 1;
              const lines = toLines(section.body);
              return (
                <div key={i} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: accent }}
                    />
                    <span className="text-[12px] font-bold uppercase tracking-wide text-gray-900">
                      {section.title}
                    </span>
                  </div>
                  <div className="space-y-1 pl-4">
                    {lines.length > 0
                      ? lines.map((line, j) => (
                          <p key={j} className="leading-snug">
                            {renderInline(line)}
                            {isLast && j === lines.length - 1 && <Cursor />}
                          </p>
                        ))
                      : isLast && (
                          <p>
                            <Cursor />
                          </p>
                        )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="whitespace-pre-wrap break-words">
            {text}
            <Cursor />
          </p>
        )}
      </div>
    </div>
  );
});
