import { useState, useRef, useEffect, useCallback, Suspense } from "react";
import { Bot, User, Copy, Check, Sparkles, ArrowDown } from "lucide-react";
import { MarkdownRenderer } from "@/components/shared/lazy-markdown";
import type { MessageResponse } from "@/lib/types/message";

/* ------------------------------------------------------------------ */
/*  TypingIndicator                                                     */
/* ------------------------------------------------------------------ */

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 pt-1">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/25 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/25 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/25 animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ChatMessage                                                         */
/* ------------------------------------------------------------------ */

interface ChatMessageProps {
  msg: MessageResponse;
  showAvatar?: boolean;
  variant?: "full" | "compact";
}

export function ChatMessage({ msg, showAvatar = true, variant = "full" }: ChatMessageProps) {
  const isUser = msg.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (variant === "compact") {
    return (
      <div className={`flex gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
        {showAvatar && (
          <div className={`shrink-0 ${!showAvatar ? "invisible" : ""}`}>
            <div
              className={`flex h-6 w-6 items-center justify-center rounded-full select-none ${
                isUser ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
              }`}
            >
              {isUser ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
            </div>
          </div>
        )}
        <div className={`max-w-[85%] min-w-0 ${isUser ? "text-right" : ""}`}>
          <div
            className={`inline-block rounded-2xl px-3 py-2 text-sm leading-relaxed ${
              isUser ? "bg-primary text-primary-foreground rounded-tr-sm" : "bg-muted rounded-tl-sm"
            }`}
          >
            {isUser ? (
              <p className="whitespace-pre-wrap break-words">{msg.content}</p>
            ) : (
              <div className="chat-markdown">
                <Suspense fallback={<span className="text-muted-foreground">...</span>}>
                  <MarkdownRenderer content={msg.content} />
                </Suspense>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Full variant — used in main conversations page
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-[18px] rounded-br-sm bg-primary text-primary-foreground px-4 py-2.5 text-sm leading-relaxed">
          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3">
      <div className="shrink-0 pt-1">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-(--brand-accent) to-orange-600">
          <Sparkles className="h-3.5 w-3.5 text-white" />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="chat-markdown text-sm leading-relaxed">
          <Suspense fallback={<span className="text-muted-foreground">...</span>}>
            <MarkdownRenderer content={msg.content} />
          </Suspense>
        </div>
        <button
          onClick={handleCopy}
          className="touch-compact mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md hover:bg-muted/60 text-muted-foreground/40 hover:text-muted-foreground"
          aria-label="Copy"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  StreamingMessage                                                    */
/* ------------------------------------------------------------------ */

export function StreamingMessage({
  content,
  variant = "full",
}: {
  content: string;
  variant?: "full" | "compact";
}) {
  if (variant === "compact") {
    return (
      <div className="flex gap-2">
        <div className="shrink-0">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Bot className="h-3 w-3" />
          </div>
        </div>
        <div className="bg-muted rounded-2xl rounded-tl-sm px-3 py-2 max-w-[85%]">
          {content ? (
            <div className="chat-markdown text-sm leading-relaxed">
              <Suspense fallback={<span className="text-muted-foreground">...</span>}>
                <MarkdownRenderer content={content} />
              </Suspense>
            </div>
          ) : (
            <TypingIndicator />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="shrink-0 pt-1">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-(--brand-accent) to-orange-600">
          <Sparkles className="h-3.5 w-3.5 text-white" />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        {content ? (
          <div className="chat-markdown text-sm leading-relaxed">
            <Suspense fallback={<span className="text-muted-foreground">...</span>}>
              <MarkdownRenderer content={content} />
            </Suspense>
          </div>
        ) : (
          <TypingIndicator />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ScrollToBottom button                                               */
/* ------------------------------------------------------------------ */

export function ScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="touch-compact absolute bottom-3 left-1/2 -translate-x-1/2 flex h-8 w-8 items-center justify-center rounded-full border bg-card/90 backdrop-blur-sm shadow-sm hover:bg-muted transition-colors z-10"
      aria-label="Scroll to bottom"
    >
      <ArrowDown className="h-3.5 w-3.5" />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  useAutoResize hook                                                  */
/* ------------------------------------------------------------------ */

export function useAutoResize(deps: unknown) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  }, [deps]);
  return ref;
}

/* ------------------------------------------------------------------ */
/*  useScrollToBottom hook                                              */
/* ------------------------------------------------------------------ */

export function useScrollToBottom() {
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    endRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  return { endRef, scrollRef, scrollToBottom };
}

/* ------------------------------------------------------------------ */
/*  useScrollVisibility hook                                            */
/* ------------------------------------------------------------------ */

export function useScrollVisibility(threshold = 80) {
  const [visible, setVisible] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (!scrollRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
      setVisible(scrollHeight - scrollTop - clientHeight > threshold);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return { scrollRef, showScrollBtn: visible };
}
