import { createContext, useContext, useState, useCallback } from "react";

interface BotBoxContextValue {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
  initialScope: "general" | "member" | null;
  initialMemberId: string | null;
  openForMember: (memberId: string) => void;
}

const BotBoxContext = createContext<BotBoxContextValue>({
  isOpen: false,
  open: () => {},
  close: () => {},
  toggle: () => {},
  initialScope: null,
  initialMemberId: null,
  openForMember: () => {},
});

export function useBotBox() {
  return useContext(BotBoxContext);
}

export function BotBoxProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [initialScope, setInitialScope] = useState<"general" | "member" | null>(null);
  const [initialMemberId, setInitialMemberId] = useState<string | null>(null);

  const open = useCallback(() => {
    setInitialScope(null);
    setInitialMemberId(null);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  const openForMember = useCallback((memberId: string) => {
    setInitialScope("member");
    setInitialMemberId(memberId);
    setIsOpen(true);
  }, []);

  return (
    <BotBoxContext.Provider
      value={{ isOpen, open, close, toggle, initialScope, initialMemberId, openForMember }}
    >
      {children}
    </BotBoxContext.Provider>
  );
}
