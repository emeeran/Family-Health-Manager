import { useEffect, useRef, useState } from "react";
import { getLatestInsight, getLatestPreConsultationNote } from "@/lib/api/members";
import type { GeneratedInsight } from "@/lib/api/members";
import type { VerificationResult } from "@/lib/types/message";

/**
 * Polls for verification status after AI generation completes.
 * Stops when verification is no longer "pending" or after max attempts.
 */
export function useVerificationPolling(
  memberId: string,
  insight: GeneratedInsight | null,
  type: "insight" | "preconsultation" = "insight"
) {
  const [verification, setVerification] = useState<VerificationResult | null>(
    insight?.verification ?? null
  );
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!insight || !memberId) return;

    // If verification is already resolved, no need to poll
    if (insight.verification && insight.verification.status !== "pending") {
      setVerification(insight.verification);
      return;
    }

    let attempts = 0;
    const maxAttempts = 24; // 2 minutes at 5s intervals

    intervalRef.current = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        setVerification({
          status: "unverifiable",
          claims_checked: 0,
          verifier_provider: "",
          summary: null,
          warnings: null,
          verified_at: "",
        });
        return;
      }

      try {
        const fetcher =
          type === "preconsultation" ? getLatestPreConsultationNote : getLatestInsight;
        const res = await fetcher(memberId);
        const data = "note" in res ? res.note : res;
        if (data?.verification && data.verification.status !== "pending") {
          setVerification(data.verification);
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch {
        // Silently retry
      }
    }, 5000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [insight?.id, memberId, type]); // eslint-disable-line react-hooks/exhaustive-deps -- insight object identity changes but we only care about id

  return verification;
}
