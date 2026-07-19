/**
 * Conditions tab — disease & condition information for a member.
 *
 * Free-text (or record-sourced) condition → NIH-normalized name + ICD-10 code
 * + MedlinePlus patient-education links. Reuses the existing ClinicalTrials
 * card so a looked-up condition also surfaces relevant trials. All sources are
 * keyless; lookups degrade to empty states on failure.
 */
import { memo, useEffect, useState } from "react";
import { Activity, ExternalLink, Info, Loader2, Search, Stethoscope } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ClinicalTrialsCard } from "@/components/members/clinical-trials-card";
import { getConditionLookup, getMemberConditions } from "@/lib/api/members";
import { ApiError } from "@/lib/api-client";
import type { ConditionLookup, MemberDetailResponse } from "@/lib/types/member";

interface ConditionsTabProps {
  data: MemberDetailResponse;
}

export const ConditionsTab = memo(function ConditionsTab({ data }: ConditionsTabProps) {
  const memberId = data.member.id;
  const [conditions, setConditions] = useState<string[] | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState("");
  const [lookup, setLookup] = useState<ConditionLookup | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingLookup, setLoadingLookup] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingList(true);
    getMemberConditions(memberId)
      .then((r) => {
        if (!cancelled) setConditions(r.conditions);
      })
      .catch(() => {
        if (!cancelled) setConditions([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [memberId]);

  async function runLookup(term: string) {
    const t = term.trim();
    if (!t) return;
    setActive(t);
    setLoadingLookup(true);
    setError(null);
    try {
      setLookup(await getConditionLookup(memberId, t));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Session expired — please refresh and sign in again."
          : "Couldn't load condition information. Please retry."
      );
      setLookup(null);
    } finally {
      setLoadingLookup(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/40 p-3">
        <Info className="h-4 w-4 mt-0.5 shrink-0 text-blue-600 dark:text-blue-400" />
        <p className="text-xs text-blue-800 dark:text-blue-300">
          Condition information is sourced from NIH (ICD-10 normalization) and MedlinePlus patient
          education — free, authoritative references. This is for awareness only and does not
          replace a clinician's diagnosis or advice.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Activity className="h-4 w-4 text-teal-500" />
            Condition Information
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runLookup(query);
            }}
            className="flex gap-2"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Look up a condition (e.g. type 2 diabetes)"
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <Button type="submit" size="sm" disabled={!query.trim() || loadingLookup}>
              {loadingLookup ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Search className="h-3.5 w-3.5" />
              )}
              Look up
            </Button>
          </form>

          <div>
            <p className="text-xs font-semibold mb-1.5 text-muted-foreground">
              {loadingList ? "Loading conditions from records…" : "From this member's records"}
            </p>
            {!loadingList && conditions && conditions.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {conditions.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => {
                      setQuery(c);
                      runLookup(c);
                    }}
                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] border transition-colors ${
                      active === c
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-muted/40 hover:bg-muted border-border"
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            ) : !loadingList ? (
              <p className="text-xs text-muted-foreground">
                No diagnoses recorded yet — search above.
              </p>
            ) : null}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {active && !error && (
            <div className="rounded-md border border-border bg-muted/20 p-3 space-y-2">
              {loadingLookup ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Looking up &ldquo;{active}&rdquo;…
                </div>
              ) : lookup ? (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Stethoscope className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-sm font-semibold">{lookup.name || lookup.query}</span>
                    {lookup.icd10_code && (
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        ICD-10: {lookup.icd10_code}
                      </span>
                    )}
                  </div>
                  {lookup.synonyms.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Also known as: {lookup.synonyms.join(", ")}
                    </p>
                  )}
                  {lookup.topics.length > 0 ? (
                    <div className="space-y-1">
                      {lookup.topics.map((t) => (
                        <a
                          key={t.url}
                          href={t.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 text-xs text-blue-600 hover:underline dark:text-blue-400"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" />
                          {t.title || "MedlinePlus patient information"}
                        </a>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No MedlinePlus education linked for this code.
                    </p>
                  )}
                </>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      {active && <ClinicalTrialsCard memberId={memberId} defaultCondition={active} />}
    </div>
  );
});
