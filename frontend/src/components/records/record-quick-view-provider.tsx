"use client";

import { createContext, useContext, useState, useCallback } from "react";

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

  return (
    <QuickViewContext.Provider
      value={{
        recordId,
        memberId,
        openQuickView,
        closeQuickView,
        isOpen: recordId !== null,
      }}
    >
      {children}
    </QuickViewContext.Provider>
  );
}
