import type { ReactNode } from "react";
import type { InsightSection } from "@/lib/parse-sections";
import { cn } from "@/lib/utils";

const KEY_ACCENT: Record<string, string> = {
  overview: "var(--chart-1)",
  conditions: "var(--destructive)",
  labs: "var(--chart-2)",
  risk: "var(--chart-3)",
  recommendations: "#06b6d4",
  follow_up: "#ec4899",
  other: "var(--muted-foreground)",
};

/** Render inline **bold**, *italic*, and `code` markdown into React nodes. */
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-foreground">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith("`")) {
      nodes.push(
        <code key={key++} className="rounded bg-muted px-1 font-mono text-[0.85em]">
          {token.slice(1, -1)}
        </code>
      );
    } else {
      nodes.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/**
 * Dense renderer for parsed insight sections. Tight 13px/snug body, compact
 * section cards keyed by semantic `key`. `variant="note"` tightens further for
 * the pre-consultation view.
 */
export function MarkdownSections({
  sections,
  variant = "report",
}: {
  sections: InsightSection[];
  variant?: "report" | "note";
}) {
  return (
    <div className="space-y-2">
      {sections.map((s, i) => {
        const accent = (s.key && KEY_ACCENT[s.key]) || "var(--muted-foreground)";
        return (
          <section
            key={i}
            className={cn(
              "rounded-md border border-border border-l-2 bg-card",
              variant === "note" ? "p-2" : "p-2.5"
            )}
            style={{ borderLeftColor: accent }}
          >
            <div className="mb-1 flex items-center gap-1.5">
              <span
                className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded text-[9px] font-bold text-white"
                style={{ backgroundColor: accent }}
              >
                {i + 1}
              </span>
              <h3 className="text-[13px] font-semibold leading-tight text-foreground">{s.title}</h3>
            </div>
            <div className="space-y-1">
              {s.body.split(/\n{2,}/).map((para, pi) =>
                para.trim() ? (
                  <p key={pi} className="text-[13px] leading-snug text-foreground/80">
                    {renderInline(para)}
                  </p>
                ) : null
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
