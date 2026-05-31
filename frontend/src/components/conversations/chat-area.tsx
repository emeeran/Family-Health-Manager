import { useState, useRef, useEffect, useCallback, Suspense, type KeyboardEvent } from "react";
import { Bot, User, Send, ArrowDown, StopCircle, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  createConversation,
  sendMessageStream,
  sendMessage,
  type StreamEvent,
} from "@/lib/api/conversations";
import type { MessageResponse, SendMessageResponse } from "@/lib/types/message";
import { toast } from "sonner";
import { MarkdownRenderer } from "@/components/shared/lazy-markdown";

/* ------------------------------------------------------------------ */
/*  Sub-components                                                      */
/* ------------------------------------------------------------------ */

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

function ChatMessage({ msg, showAvatar }: { msg: MessageResponse; showAvatar: boolean }) {
  const isUser = msg.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`group flex gap-2.5 ${isUser ? "flex-row-reverse" : ""} ${showAvatar ? "mt-5" : "mt-1"}`}
    >
      {/* Avatar — visible only at group boundaries */}
      <div className={`shrink-0 ${showAvatar ? "" : "invisible"}`}>
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-full select-none ${
            isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
          }`}
        >
          {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </div>
      </div>

      {/* Bubble */}
      <div className={`max-w-[80%] min-w-0 flex flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div className="relative group/bubble">
          <div
            className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
              isUser
                ? "bg-primary text-primary-foreground rounded-tr-sm"
                : "bg-muted/70 rounded-tl-sm"
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
          {/* Copy action — assistant only, on hover */}
          {!isUser && (
            <button
              onClick={handleCopy}
              className="absolute -bottom-6 left-0 opacity-0 group-hover/bubble:opacity-100 transition-opacity p-1 rounded hover:bg-muted text-muted-foreground"
              aria-label="Copy"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function DateSeparator({ date }: { date: string }) {
  const label = (() => {
    const d = new Date(date + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
    if (diff === 0) return "Today";
    if (diff === 1) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  })();

  return (
    <div className="flex items-center gap-3 my-3">
      <div className="flex-1 h-px bg-border/60" />
      <span className="text-[11px] text-muted-foreground/60">{label}</span>
      <div className="flex-1 h-px bg-border/60" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Suggestion chips                                                    */
/* ------------------------------------------------------------------ */

const SUGGESTIONS = [
  "Summarize my family's recent health activity",
  "What medications is my family currently taking?",
  "Any overdue health reminders?",
];

/* ------------------------------------------------------------------ */
/*  ChatArea                                                            */
/* ------------------------------------------------------------------ */

interface ChatAreaProps {
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
  scope: "general" | "member";
  familyMemberId: string | null;
  initialMessages?: MessageResponse[];
}

export function ChatArea({
  conversationId,
  onConversationCreated,
  scope,
  familyMemberId,
  initialMessages,
}: ChatAreaProps) {
  const [messages, setMessages] = useState<MessageResponse[]>(initialMessages ?? []);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    chatEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  // Sync initial messages when conversationId changes
  useEffect(() => {
    setMessages(initialMessages ?? []);
  }, [conversationId, initialMessages]);

  // Auto-scroll
  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, streamingContent, scrollToBottom]);

  // Scroll button visibility
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (!scrollRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
      setShowScrollBtn(scrollHeight - scrollTop - clientHeight > 100);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [conversationId]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  }, [input]);

  function getMessageDate(msg: MessageResponse) {
    return new Date(msg.created_at).toISOString().slice(0, 10);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;

    setSending(true);
    setStreamingContent("");
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    let activeConvId = conversationId;

    // Auto-create conversation if none exists
    if (!activeConvId) {
      try {
        const conv = await createConversation({
          scope,
          family_member_id: scope === "member" ? familyMemberId : null,
          title: text.slice(0, 60),
        });
        activeConvId = conv.id;
        onConversationCreated(conv.id);
      } catch {
        toast.error("Failed to create conversation");
        setSending(false);
        setInput(text);
        return;
      }
    }

    // Optimistic user message
    const optimisticUserMsg: MessageResponse = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConvId,
      role: "user" as const,
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);

    try {
      let streamedText = "";

      await sendMessageStream(activeConvId, { content: text }, (event: StreamEvent) => {
        if (event.stage === "user_message") {
          const realId = event.id as string;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === optimisticUserMsg.id
                ? { ...m, id: realId, created_at: (event.created_at as string) || m.created_at }
                : m
            )
          );
        } else if (event.stage === "token") {
          streamedText += event.content as string;
          setStreamingContent(streamedText);
        } else if (event.stage === "complete") {
          const assistantMsg = event.assistant_message as MessageResponse;
          setStreamingContent("");
          setMessages((prev) => [...prev, assistantMsg]);
        } else if (event.stage === "error") {
          toast.error((event.message as string) || "AI service unavailable");
          setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMsg.id));
          setInput(text);
        }
      });
    } catch {
      try {
        setStreamingContent("");
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMsg.id));
        const response: SendMessageResponse = await sendMessage(activeConvId, { content: text });
        setMessages((prev) => [...prev, response.user_message, response.assistant_message]);
      } catch {
        toast.error("Failed to send message");
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMsg.id));
        setInput(text);
      }
    } finally {
      setSending(false);
      setStreamingContent("");
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const isEmpty = messages.length === 0 && !sending;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Messages */}
      <div className="relative flex-1 min-h-0">
        <div ref={scrollRef} className="absolute inset-0 overflow-y-auto scroll-smooth">
          <div className="mx-auto max-w-3xl px-4 py-4">
            {isEmpty ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted mb-3">
                  <Bot className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground max-w-xs mb-4">
                  Ask about health records, medications, or lab results.
                </p>
                <div className="flex flex-col gap-1 w-full max-w-xs">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => {
                        setInput(s);
                        textareaRef.current?.focus();
                      }}
                      className="text-left text-xs rounded-md border px-3 py-2 text-muted-foreground hover:bg-muted/50 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, idx) => {
                  const showAvatar = idx === 0 || messages[idx - 1]?.role !== msg.role;
                  const showDate =
                    idx === 0 || getMessageDate(msg) !== getMessageDate(messages[idx - 1]);

                  return (
                    <div key={msg.id}>
                      {showDate && <DateSeparator date={getMessageDate(msg)} />}
                      <ChatMessage msg={msg} showAvatar={showAvatar} />
                    </div>
                  );
                })}

                {/* Streaming */}
                {sending && (
                  <div className="flex gap-2.5 mt-5">
                    <div className="shrink-0">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
                        <Bot className="h-3.5 w-3.5" />
                      </div>
                    </div>
                    <div className="bg-muted/70 rounded-2xl rounded-tl-sm px-3.5 py-2.5 max-w-[80%]">
                      {streamingContent ? (
                        <div className="chat-markdown text-sm leading-relaxed">
                          <Suspense fallback={<span className="text-muted-foreground">...</span>}>
                            <MarkdownRenderer content={streamingContent} />
                          </Suspense>
                        </div>
                      ) : (
                        <TypingIndicator />
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            <div ref={chatEndRef} className="h-2" />
          </div>
        </div>

        {/* Scroll-to-bottom */}
        {showScrollBtn && (
          <button
            onClick={() => scrollToBottom()}
            className="absolute bottom-2 left-1/2 -translate-x-1/2 flex h-8 w-8 items-center justify-center rounded-full border bg-background/90 backdrop-blur-sm shadow-sm hover:bg-muted transition-colors z-10"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t px-3 py-2">
        <div className="mx-auto max-w-3xl flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message..."
            aria-label="Type your message"
            disabled={sending}
            rows={1}
            className="flex-1 resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 max-h-36"
          />
          <Button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            size="icon"
            className="h-9 w-9 shrink-0 rounded-lg"
          >
            {sending ? (
              <StopCircle className="h-4 w-4 animate-pulse" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
