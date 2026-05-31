import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from "react";
import { Send, StopCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  createConversation,
  sendMessageStream,
  sendMessage,
  type StreamEvent,
} from "@/lib/api/conversations";
import type { MessageResponse, SendMessageResponse } from "@/lib/types/message";
import { toast } from "sonner";
import {
  ChatMessage,
  StreamingMessage,
  ScrollToBottomButton,
  useAutoResize,
  useScrollToBottom,
  useScrollVisibility,
} from "@/components/shared/chat-primitives";

/* ------------------------------------------------------------------ */
/*  Suggestions                                                         */
/* ------------------------------------------------------------------ */

const SUGGESTIONS = [
  { icon: "📋", text: "Summarize my family's recent health activity" },
  { icon: "💊", text: "What medications is my family taking?" },
  { icon: "⏰", text: "Any overdue health reminders?" },
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

  const { endRef, scrollRef: mainScrollRef, scrollToBottom } = useScrollToBottom();
  const { scrollRef: visScrollRef, showScrollBtn } = useScrollVisibility(80);
  const textareaRef = useAutoResize(input);

  // Combine scroll refs
  const scrollRef = useRef<HTMLDivElement>(null);
  const setScrollRef = useCallback(
    (el: HTMLDivElement | null) => {
      (scrollRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
      (mainScrollRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
      (visScrollRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    },
    [mainScrollRef, visScrollRef]
  );

  useEffect(() => {
    setMessages(initialMessages ?? []);
  }, [conversationId, initialMessages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, streamingContent, scrollToBottom]);

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!text || sending) return;

    setSending(true);
    setStreamingContent("");
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    let activeConvId = conversationId;

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
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Scrollable message area ── */}
      <div className="relative flex-1 min-h-0">
        <div ref={setScrollRef} className="absolute inset-0 overflow-y-auto scroll-smooth">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center h-full px-4 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-(--brand-accent)/15 to-orange-200/60 dark:to-orange-900/20 mb-5">
                <Sparkles className="h-7 w-7 text-(--brand-accent)" />
              </div>
              <h2 className="text-2xl font-semibold text-foreground mb-1.5">How can I help?</h2>
              <p className="text-sm text-muted-foreground max-w-md mb-8 leading-relaxed">
                Ask about health records, medications, lab results, or reminders for your family.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.text}
                    onClick={() => handleSend(s.text)}
                    className="text-left text-[13px] rounded-xl border border-border/50 bg-card/60 px-3.5 py-3 text-foreground/70 hover:bg-card hover:border-border hover:text-foreground/90 transition-all"
                  >
                    <span className="block mb-1">{s.icon}</span>
                    {s.text}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl px-4 sm:px-6 py-6 pb-2">
              <div className="space-y-6">
                {messages.map((msg) => (
                  <ChatMessage key={msg.id} msg={msg} />
                ))}
                {sending && <StreamingMessage content={streamingContent} />}
              </div>
              <div ref={endRef} className="h-4" />
            </div>
          )}
        </div>

        {showScrollBtn && <ScrollToBottomButton onClick={() => scrollToBottom()} />}
      </div>

      {/* ── Input bar — always pinned to bottom ── */}
      <div className="shrink-0 bg-background/80 backdrop-blur-sm border-t border-border/40 px-3 sm:px-6 pt-3 pb-4">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-end gap-2 rounded-2xl bg-card border px-4 py-2.5 shadow-sm focus-within:border-ring/40 focus-within:shadow-md transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Health Keeper..."
              aria-label="Type your message"
              disabled={sending}
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm leading-relaxed placeholder:text-muted-foreground/50 focus-visible:outline-none disabled:opacity-50 max-h-36 py-0.5"
            />
            <Button
              onClick={() => handleSend()}
              disabled={sending || !input.trim()}
              size="icon"
              className="h-8 w-8 shrink-0 rounded-full"
            >
              {sending ? (
                <StopCircle className="h-4 w-4 animate-pulse" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground/40">
            AI may produce inaccurate information. Verify important health details.
          </p>
        </div>
      </div>
    </div>
  );
}
