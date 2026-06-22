import { createContext, useContext, useState, useCallback, useMemo } from "react";

interface QuickViewContextValue {
  recordId: string | null;
  memberId: string | null;
  openQuickView: (recordId: string, memberId: string) => void;
  closeQuickView: () => void;
  isOpen: boolean;
}

const QuickViewContext = createContext<QuickViewContextValue>({
  recordId: null,
  memberId: null,
  openQuickView: () => {},
  closeQuickView: () => {},
  isOpen: false,
});

export function useRecordQuickView() {
  return useContext(QuickViewContext);
}

export function RecordQuickViewProvider({ children }: { children: React.ReactNode }) {
  const [recordId, setRecordId] = useState<string | null>(null);
  const [memberId, setMemberId] = useState<string | null>(null);

  const openQuickView = useCallback((recId: string, memId: string) => {
    setRecordId(recId);
    setMemberId(memId);
  }, []);

  const closeQuickView = useCallback(() => {
    setRecordId(null);
    setMemberId(null);
  }, []);

  // Memoize so the context value is stable across renders that don't change
  // open/close state — this provider wraps the whole app, so without this every
  // consumer of useRecordQuickView re-renders whenever the provider re-renders.
  const value = useMemo<QuickViewContextValue>(
    () => ({ recordId, memberId, openQuickView, closeQuickView, isOpen: recordId !== null }),
    [recordId, memberId, openQuickView, closeQuickView]
  );

  return <QuickViewContext.Provider value={value}>{children}</QuickViewContext.Provider>;
}
