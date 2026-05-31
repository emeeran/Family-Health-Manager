import { createContext, useContext, useState, useCallback } from "react";

interface BotBoxContextValue {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
}

const BotBoxContext = createContext<BotBoxContextValue>({
  isOpen: false,
  open: () => {},
  close: () => {},
  toggle: () => {},
});

export function useBotBox() {
  return useContext(BotBoxContext);
}

export function BotBoxProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  return (
    <BotBoxContext.Provider value={{ isOpen, open, close, toggle }}>
      {children}
    </BotBoxContext.Provider>
  );
}
