import { useEffect, type RefObject } from "react";

/**
 * Scroll the first `[role="alert"]` inside `containerRef` into view whenever
 * `errorSignature` becomes non-empty (and again if it changes).
 *
 * Used by the record-form wizard steps so that, after the wizard jumps to the
 * failing step on validation, the user actually lands on the errored field
 * rather than the top of the step.
 *
 * A `requestAnimationFrame` defers the lookup so the step content has mounted
 * (validation can switch which step is rendered in the same tick).
 */
export function useScrollToFirstError(
  containerRef: RefObject<HTMLElement | null>,
  errorSignature: string
) {
  useEffect(() => {
    if (!errorSignature) return;
    const id = requestAnimationFrame(() => {
      const el = containerRef.current?.querySelector<HTMLElement>("[role='alert']");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => cancelAnimationFrame(id);
  }, [errorSignature, containerRef]);
}
