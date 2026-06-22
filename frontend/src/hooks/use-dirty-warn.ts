import { useEffect } from "react";

/**
 * Warns the user when they try to navigate away with unsaved form changes.
 * @param dirty - whether the form has been modified
 * @param isPending - whether a form submission is in progress
 */
export function useDirtyWarn(dirty: boolean, isPending: boolean) {
  useEffect(() => {
    if (!dirty || isPending) return;

    function handler(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty, isPending]);
}
