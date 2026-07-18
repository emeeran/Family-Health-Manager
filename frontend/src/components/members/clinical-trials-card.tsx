import { useState, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FlaskConical, ExternalLink, Loader2, Search } from "lucide-react";
import { getClinicalTrials } from "@/lib/api/members";
import { ApiError } from "@/lib/api-client";
import type { ClinicalTrial } from "@/lib/types/member";

interface ClinicalTrialsCardProps {
  memberId: string;
  /** Optional default condition to pre-fill (e.g. the member's diagnosis). */
  defaultCondition?: string;
}

const STATUS_STYLE: Record<string, string> = {
  RECRUITING: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300",
  "NOT YET RECRUITING": "bg-blue-100 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300",
  COMPLETED: "bg-muted text-muted-foreground",
};

export const ClinicalTrialsCard = memo(function ClinicalTrialsCard({
  memberId,
  defaultCondition = "",
}: ClinicalTrialsCardProps) {
  const [condition, setCondition] = useState(defaultCondition);
  const [query, setQuery] = useState(defaultCondition);
  const [trials, setTrials] = useState<ClinicalTrial[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setCondition(q);
    try {
      const result = await getClinicalTrials(memberId, q);
      setTrials(result.trials);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Session expired — please refresh and sign in again."
          : "Couldn't search clinical trials. Please retry."
      );
      setTrials([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-teal-500" />
          Clinical Trials
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex gap-2 mb-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="Condition (e.g. Type 2 diabetes)"
            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button size="sm" onClick={search} disabled={loading || !query.trim()}>
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Search
          </Button>
        </div>

        {error && <p className="text-sm text-destructive font-medium">{error}</p>}

        {trials !== null && !error && (
          <div className="space-y-2">
            {trials.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No trials found for &ldquo;{condition}&rdquo;.
              </p>
            ) : (
              trials.map((t) => (
                <a
                  key={t.nct_id}
                  href={t.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-md border border-border p-2.5 hover:bg-muted/40 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-medium leading-snug">{t.title}</p>
                    {t.status && (
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                          STATUS_STYLE[t.status] || "bg-muted text-muted-foreground"
                        }`}
                      >
                        {t.status.replace(/_/g, " ").toLowerCase()}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground">
                    <span className="font-mono">{t.nct_id}</span>
                    {t.phase && <span>· {t.phase}</span>}
                    <span className="inline-flex items-center gap-0.5 text-blue-600 dark:text-blue-400">
                      <ExternalLink className="h-2.5 w-2.5" /> clinicaltrials.gov
                    </span>
                  </div>
                </a>
              ))
            )}
          </div>
        )}
        <p className="mt-2 text-[10px] text-muted-foreground/70">
          Source: ClinicalTrials.gov. For awareness only — not a recommendation to enroll.
        </p>
      </CardContent>
    </Card>
  );
});
