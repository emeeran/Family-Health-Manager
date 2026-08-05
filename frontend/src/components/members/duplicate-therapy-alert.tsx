/**
 * Advisory banner shown on the member's medication view when the backend's
 * deterministic duplicate-therapy check flags ≥2 active meds from the same
 * therapeutic class (e.g. two statins, ACE inhibitor + ARB). Purely advisory —
 * never blocks edits, hidden when there are no findings.
 */

import useSWR from "swr";
import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { getDuplicateTherapy } from "@/lib/api/members";

interface DuplicateTherapyAlertProps {
  memberId: string;
}

export function DuplicateTherapyAlert({ memberId }: DuplicateTherapyAlertProps) {
  const { data } = useSWR(`duplicate-therapy-${memberId}`, () => getDuplicateTherapy(memberId), {
    revalidateOnFocus: false,
    dedupingInterval: 60_000,
  });

  const findings = data?.findings ?? [];
  if (findings.length === 0) return null;

  return (
    <Alert className="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/50 dark:bg-amber-950/30 dark:text-amber-200">
      <AlertTriangle className="text-amber-600 dark:text-amber-400" />
      <AlertTitle className="text-amber-900 dark:text-amber-200">
        Possible duplicate therapy
      </AlertTitle>
      <AlertDescription className="text-amber-800 dark:text-amber-300">
        <ul className="mt-1 space-y-1">
          {findings.map((f) => (
            <li key={f.therapeutic_class}>
              <span className="font-medium">{f.therapeutic_class}:</span> {f.medications.join(", ")}
              .{" "}
              <span className="text-amber-700 dark:text-amber-400/80">
                Review with your doctor.
              </span>
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
