import { useState, useRef, useEffect, lazy, Suspense, useCallback } from "react";
import { Bot, User, Send, Sparkles, Loader2, Trash2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
  listConversations,
  createConversation,
  getConversation,
  sendMessage,
  deleteConversation,
  getMessageVerification,
} from "@/lib/api/conversations";
import type { MessageResponse } from "@/lib/types/message";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { VerificationBadge } from "./verification-badge";

// Lazy-load markdown renderer — ~150KB saved from initial chunk
const MarkdownRenderer = lazy(async () => {
  const [{ default: ReactMarkdown }, { default: remarkGfm }] = await Promise.all([
    import("react-markdown"),
    import("remark-gfm"),
  ]);
  return {
    default: ({ content }: { content: string }) => (
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    ),
  };
});

/* ── Sub-components ── */

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-0.5">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

function ChatMessage({ msg, showAvatar }: { msg: MessageResponse; showAvatar: boolean }) {
  const isUser = msg.role === "user";

  return (
    <div
      className={cn("flex gap-2.5", isUser && "flex-row-reverse", showAvatar ? "mt-4" : "mt-0.5")}
    >
      <div className={cn("shrink-0 mt-0.5", !showAvatar && "invisible")}>
        <div
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold select-none",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300"
          )}
        >
          {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </div>
      </div>
      <div className={cn("max-w-[85%] min-w-0 space-y-0.5 flex flex-col", isUser && "items-end")}>
        {showAvatar && (
          <div className={cn("flex items-center gap-1.5 px-1", isUser && "flex-row-reverse")}>
            <span className="text-[11px] font-medium text-foreground">
              {isUser ? "You" : "Health AI"}
            </span>
            <span className="text-xs text-muted-foreground">
              {new Date(msg.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        )}
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-md"
              : "bg-muted/80 rounded-tl-md"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{msg.content}</p>
          ) : (
            <div className="chat-markdown">
              <Suspense
                fallback={<span className="text-muted-foreground text-xs">Loading...</span>}
              >
                <MarkdownRenderer content={msg.content} />
              </Suspense>
            </div>
          )}
        </div>
        {/* Verification badge — only on assistant messages */}
        {!isUser && msg.verification && (
          <div className="px-1">
            <VerificationBadge verification={msg.verification} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Suggestion chips ── */

const SUGGESTIONS = [
  "Summarize my family's recent health activity",
  "What medications is my family currently taking?",
  "Any overdue health reminders?",
];

/* ── Main component ── */

interface ChatPopupProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChatPopup({ open, onOpenChange }: ChatPopupProps) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Cache conversation ID across open/close cycles to avoid re-fetching
  const cachedConversationIdRef = useRef<string | null>(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // Load or create conversation when popup opens (uses cached ID if available)
  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function init() {
      // If we already have a cached conversation ID, reuse it without re-fetching
      const cachedId = cachedConversationIdRef.current;
      if (cachedId) {
        setConversationId(cachedId);
        setLoading(true);
        try {
          const detail = await getConversation(cachedId);
          if (cancelled) return;
          setMessages(detail.messages);
        } catch {
          if (!cancelled) toast.error("Failed to load conversation");
        } finally {
          if (!cancelled) setLoading(false);
        }
        return;
      }

      setLoading(true);
      try {
        // Find existing general conversation
        const convs = await listConversations();
        if (cancelled) return;

        const general = convs.find((c) => c.scope === "general");

        let convId: string;
        if (general) {
          convId = general.id;
        } else {
          const created = await createConversation({
            scope: "general",
            title: "Health Assistant",
          });
          if (cancelled) return;
          convId = created.id;
        }

        setConversationId(convId);
        cachedConversationIdRef.current = convId;

        // Load messages
        const detail = await getConversation(convId);
        if (cancelled) return;
        setMessages(detail.messages);
      } catch {
        if (!cancelled) toast.error("Failed to load conversations");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [input]);

  /** Poll for verification result when status is pending */
  const pollVerification = useCallback((convId: string, msgId: string) => {
    // Clear any previous polling before starting a new one
    if (pollingRef.current) clearInterval(pollingRef.current);

    let attempts = 0;
    const maxAttempts = 15; // 15 seconds max

    pollingRef.current = setInterval(async () => {
      attempts++;
      try {
        const result = await getMessageVerification(convId, msgId);
        if (result.status !== "pending") {
          // Update the message with verification data
          setMessages((prev) =>
            prev.map((m) => (m.id === msgId ? { ...m, verification: result } : m))
          );
          if (pollingRef.current) clearInterval(pollingRef.current);
        }
      } catch {
        // 404 or other error — stop polling
        if (pollingRef.current) clearInterval(pollingRef.current);
      }
      if (attempts >= maxAttempts && pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    }, 1000);
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || sending || !conversationId) return;

    setInput("");
    setSending(true);

    // Clear previous polling
    if (pollingRef.current) clearInterval(pollingRef.current);

    try {
      const result = await sendMessage(conversationId, { content: trimmed });

      // Attach inline verification if present
      const assistantMsg: MessageResponse = {
        ...result.assistant_message,
        verification: result.verification ?? result.assistant_message.verification,
      };

      setMessages((prev) => [...prev, result.user_message, assistantMsg]);

      // If verification is pending, start polling
      if (assistantMsg.verification?.status === "pending") {
        pollVerification(conversationId, assistantMsg.id);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to send message";
      toast.error(msg);
      // Restore input on failure so user doesn't lose their message
      setInput(trimmed);
    } finally {
      setSending(false);
    }
  }, [input, sending, conversationId, pollVerification]);

  const handleClear = useCallback(async () => {
    if (!conversationId) return;

    if (pollingRef.current) clearInterval(pollingRef.current);

    try {
      await deleteConversation(conversationId);
      // Create a fresh conversation so user can keep chatting
      const created = await createConversation({
        scope: "general",
        title: "Health Assistant",
      });
      setMessages([]);
      setConversationId(created.id);
      cachedConversationIdRef.current = created.id;
    } catch {
      toast.error("Failed to clear conversation");
    }
  }, [conversationId]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full sm:max-w-[420px] p-0 flex flex-col h-full"
      >
        {/* Header */}
        <SheetHeader className="flex-row items-center gap-2.5 border-b p-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20">
            <Sparkles className="h-4 w-4 text-(--brand-accent)" />
          </div>
          <div className="flex-1 min-w-0">
            <SheetTitle className="text-sm font-semibold">Health AI Assistant</SheetTitle>
            <SheetDescription className="text-[11px]">
              Ask about your family&apos;s health
            </SheetDescription>
          </div>
          {messages.length > 0 && (
            <Button variant="ghost" size="icon-sm" onClick={handleClear} title="Clear conversation">
              <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
            </Button>
          )}
          <Button variant="ghost" size="icon-sm" onClick={() => onOpenChange(false)}>
            ✕
          </Button>
        </SheetHeader>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-smooth">
          <div className="px-4 py-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 mb-3">
                  <Bot className="h-6 w-6 text-violet-600 dark:text-violet-400" />
                </div>
                <h3 className="text-sm font-semibold mb-1">How can I help?</h3>
                <p className="text-xs text-muted-foreground max-w-[260px] mb-4">
                  Ask about health records, medications, lab results, or general health topics.
                </p>
                <div className="flex flex-col gap-1.5 w-full max-w-[280px]">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => {
                        setInput(s);
                        textareaRef.current?.focus();
                      }}
                      className="text-left text-xs rounded-lg border px-3 py-2 text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => {
                const showAvatar = idx === 0 || messages[idx - 1]?.role !== msg.role;
                return <ChatMessage key={msg.id} msg={msg} showAvatar={showAvatar} />;
              })
            )}

            {/* Typing indicator */}
            {sending && (
              <div className="flex gap-2.5 mt-4">
                <div className="shrink-0 mt-0.5">
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300">
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                </div>
                <div className="bg-muted/80 rounded-2xl rounded-tl-md px-3.5 py-2.5">
                  <TypingIndicator />
                </div>
              </div>
            )}

            <div ref={chatEndRef} className="h-2" />
          </div>
        </div>

        {/* Input */}
        <div className="shrink-0 border-t px-3 py-2.5">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your health..."
              disabled={sending || loading}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-input bg-transparent px-3.5 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 max-h-40"
            />
            <Button
              onClick={handleSend}
              disabled={sending || !input.trim() || loading}
              size="icon"
              className="h-9 w-9 shrink-0 rounded-xl"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="text-center mt-1 text-xs text-muted-foreground/50">
            AI may make mistakes. Verify important info.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
