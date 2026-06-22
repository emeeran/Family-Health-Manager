import { useState } from "react";
import { LayoutGrid, List } from "lucide-react";

export type ViewMode = "grid" | "list";

interface ViewToggleProps {
  value: ViewMode;
  onChange: (view: ViewMode) => void;
}

export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div className="flex items-center rounded-lg border border-border/60 overflow-hidden">
      <button
        onClick={() => onChange("grid")}
        className={`p-2 transition-colors ${
          value === "grid"
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:text-foreground"
        }`}
        aria-label="Grid view"
      >
        <LayoutGrid className="h-4 w-4" />
      </button>
      <button
        onClick={() => onChange("list")}
        className={`p-2 transition-colors ${
          value === "list"
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:text-foreground"
        }`}
        aria-label="List view"
      >
        <List className="h-4 w-4" />
      </button>
    </div>
  );
}

/**
 * Hook to persist view mode preference in localStorage.
 * Uses the same pattern as members-content.tsx.
 */
export function useViewPreference(storageKey: string, fallback: ViewMode = "grid") {
  const [view, setView] = useState<ViewMode>(() => {
    if (typeof window === "undefined") return fallback;
    return (localStorage.getItem(storageKey) as ViewMode) || fallback;
  });

  function setViewWithPersistence(v: ViewMode) {
    setView(v);
    localStorage.setItem(storageKey, v);
  }

  return [view, setViewWithPersistence] as const;
}
