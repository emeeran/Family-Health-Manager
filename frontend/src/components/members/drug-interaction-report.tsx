import { useState, useEffect, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CheckCircle2, Loader2, ShieldAlert, Shield, ShieldOff } from "lucide-react";
import { getDrugInteractions, getLatestDrugInteractions } from "@/lib/api/members";
import type { DrugInteraction } from "@/lib/types/member";

interface DrugInteractionReportProps {
  memberId: string;
  medicationCount: number;
}

const SEVERITY = {
  high: {
    icon: ShieldAlert,
    bg: "bg-red-50 border-red-200 dark:bg-red-950/50 dark:border-red-800",
    badge: "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-300",
    iconColor: "text-red-600 dark:text-red-400",
    label: "High Risk",
  },
  moderate: {
    icon: Shield,
    bg: "bg-amber-50 border-amber-200 dark:bg-amber-950/50 dark:border-amber-800",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300",
    iconColor: "text-amber-600 dark:text-amber-400",
    label: "Moderate",
  },
  low: {
    icon: ShieldOff,
    bg: "bg-blue-50 border-blue-200 dark:bg-blue-950/50 dark:border-blue-800",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300",
    iconColor: "text-blue-600 dark:text-blue-400",
    label: "Low Risk",
  },
};

export const DrugInteractionReport = memo(function DrugInteractionReport({
  memberId,
  medicationCount,
}: DrugInteractionReportProps) {
  const [interactions, setInteractions] = useState<DrugInteraction[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Auto-fetch latest on mount
  useEffect(() => {
    if (medicationCount < 2) {
      setInitialLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const result = await getLatestDrugInteractions(memberId);
        if (!cancelled) {
          setInteractions(result.interactions);
        }
      } catch {
        // Auto-generation may fail, user can retry
      } finally {
        if (!cancelled) setInitialLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [memberId, medicationCount]);

  async function checkInteractions() {
    setLoading(true);
    setError(null);
    try {
      const result = await getDrugInteractions(memberId);
      setInteractions(result.interactions);
    } catch {
      setError("Failed to check interactions. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  // Not enough medications for interactions
  if (medicationCount < 2) {
    return (
      <Card className="flex flex-col overflow-hidden">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Drug Interactions
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="flex-1 pt-0">
          <p className="text-xs text-muted-foreground">
            At least 2 active medications are needed to check interactions.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-orange-500" />
            Drug Interactions
          </CardTitle>
          <Button
            onClick={checkInteractions}
            size="sm"
            variant="ghost"
            disabled={loading}
            className="text-xs h-7"
          >
            {loading ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : interactions !== null ? (
              "Re-check"
            ) : (
              "Check"
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex-1 pt-0">
        {initialLoading && (
          <div className="flex items-center gap-3 py-4">
            <Loader2 className="h-4 w-4 animate-spin text-foreground/40" />
            <span className="text-sm text-foreground/60">
              Checking {medicationCount} medications...
            </span>
          </div>
        )}

        {!initialLoading && loading && (
          <div className="flex items-center gap-3 py-4">
            <Loader2 className="h-5 w-5 animate-spin text-foreground/40" />
            <span className="text-sm text-foreground/60">
              Analyzing {medicationCount} medications...
            </span>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive font-medium">
            {error}
          </div>
        )}

        {!initialLoading && !loading && interactions !== null && (
          <>
            {interactions.length === 0 ? (
              <div className="flex items-center gap-3 py-3 px-3 rounded-lg bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800">
                <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                    No interactions found
                  </p>
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">
                    {medicationCount} medications analyzed — all clear.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-destructive">
                    {interactions.length} interaction{interactions.length !== 1 ? "s" : ""} found
                  </span>
                </div>
                {interactions.map((interaction, idx) => {
                  const config = SEVERITY[interaction.severity] || SEVERITY.moderate;
                  const Icon = config.icon;
                  return (
                    <div key={idx} className={`rounded-lg border p-3 ${config.bg}`}>
                      <div className="flex items-start gap-2.5">
                        <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${config.iconColor}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-bold">
                              {interaction.drugs.join(" + ")}
                            </span>
                            <span
                              className={`inline-flex items-center px-2 py-0.5 text-xs font-bold rounded uppercase tracking-wider ${config.badge}`}
                            >
                              {config.label}
                            </span>
                          </div>
                          <p className="text-sm text-foreground/80">{interaction.description}</p>
                          <p className="text-sm text-foreground/60 mt-1.5">
                            <span className="font-semibold">Recommendation:</span>{" "}
                            {interaction.recommendation}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
});
