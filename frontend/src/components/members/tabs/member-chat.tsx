import { useState, useRef, useEffect, useCallback, Suspense, type KeyboardEvent } from "react";
import { Send, ArrowDown, StopCircle, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  createConversation,
  sendMessageStream,
  sendMessage,
  getConversation,
  listConversations,
  type StreamEvent,
} from "@/lib/api/conversations";
import type { MessageResponse } from "@/lib/types/message";
import { MarkdownRenderer } from "@/components/shared/lazy-markdown";
import { toast } from "sonner";

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
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

function ChatMessage({ msg }: { msg: MessageResponse }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="shrink-0 h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center mt-0.5">
          <Bot className="h-3.5 w-3.5 text-primary" />
        </div>
      )}
      <div
        className={`group/bubble relative max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        <div className={isUser ? "" : "chat-markdown"}>
          <Suspense fallback={<span className="text-muted-foreground">...</span>}>
            <MarkdownRenderer content={msg.content} />
          </Suspense>
        </div>
      </div>
      {isUser && (
        <div className="shrink-0 h-6 w-6 rounded-full bg-muted flex items-center justify-center mt-0.5">
          <User className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

const MEMBER_SUGGESTIONS = [
  "Summarize this member's health records",
  "What are the active medications and interactions?",
  "Generate a care summary for the next doctor visit",
];

/* ------------------------------------------------------------------ */
/*  MemberChat                                                          */
/* ------------------------------------------------------------------ */

interface MemberChatProps {
  memberId: string;
  memberName: string;
}

export function MemberChat({ memberId, memberName }: MemberChatProps) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    chatEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  /* Find or create a member-scoped conversation on mount */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const convs = await listConversations();
        if (cancelled) return;
        const existing = convs.find((c) => c.family_member_id === memberId && c.scope === "member");
        if (existing) {
          setConversationId(existing.id);
          // Fetch existing messages
          const detail = await getConversation(existing.id);
          if (!cancelled) {
            setMessages(detail.messages);
          }
        }
      } catch {
        // ignore — will create on first message
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [memberId]);

  /* Auto-scroll on new messages */
  useEffect(() => {
    if (messages.length > 0 || streamingContent) {
      scrollToBottom();
    }
  }, [messages.length, streamingContent, scrollToBottom]);

  /* Scroll button visibility */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(gap > 120);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  /* Auto-resize textarea */
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }, [input]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    // Optimistic user message
    const tempMsg: MessageResponse = {
      id: `temp-${Date.now()}`,
      conversation_id: conversationId ?? "",
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempMsg]);

    try {
      let convId = conversationId;

      // Create conversation if needed
      if (!convId) {
        const conv = await createConversation({
          scope: "member",
          family_member_id: memberId,
          title: `Chat — ${memberName}`,
        });
        convId = conv.id;
        setConversationId(convId);
      }

      // Try streaming first
      let fullContent = "";
      try {
        await sendMessageStream(convId, { content: text }, (event: StreamEvent) => {
          if (event.type === "token" && typeof event.content === "string") {
            fullContent += event.content;
            setStreamingContent(fullContent);
          }
        });
      } catch {
        // Fallback to non-streaming
        const result = await sendMessage(convId, { content: text });
        fullContent = result.assistant_message.content;
      }

      setStreamingContent("");

      // Replace temp user message + add assistant response
      const assistantMsg: MessageResponse = {
        id: `resp-${Date.now()}`,
        conversation_id: convId,
        role: "assistant",
        content: fullContent,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempMsg.id),
        { ...tempMsg, id: `user-${Date.now()}`, conversation_id: convId },
        assistantMsg,
      ]);
    } catch {
      toast.error("Failed to send message");
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id));
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (!loaded) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">Loading chat...</p>
      </div>
    );
  }

  const isEmpty = messages.length === 0 && !streamingContent;

  return (
    <div
      className="flex flex-col border rounded-lg bg-background relative"
      style={{ height: "min(520px, 60vh)" }}
    >
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 relative">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium">Chat about {memberName}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Ask questions about their health records, medications, or care plan.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2 justify-center max-w-md">
              {MEMBER_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setInput(s);
                    textareaRef.current?.focus();
                  }}
                  className="text-xs px-2.5 py-1.5 rounded-full border bg-background hover:bg-muted transition-colors cursor-pointer"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}

        {streamingContent && (
          <div className="flex gap-2 justify-start">
            <div className="shrink-0 h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center mt-0.5">
              <Bot className="h-3.5 w-3.5 text-primary" />
            </div>
            <div className="max-w-[80%] rounded-2xl px-3 py-2 text-sm bg-muted">
              <div className="chat-markdown">
                <Suspense fallback={<span className="text-muted-foreground">...</span>}>
                  <MarkdownRenderer content={streamingContent} />
                </Suspense>
              </div>
            </div>
          </div>
        )}

        {sending && !streamingContent && (
          <div className="flex gap-2 justify-start">
            <div className="shrink-0 h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center mt-0.5">
              <Bot className="h-3.5 w-3.5 text-primary" />
            </div>
            <div className="rounded-2xl px-3 py-2 bg-muted">
              <TypingIndicator />
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Scroll-to-bottom */}
      {showScrollBtn && (
        <button
          onClick={() => scrollToBottom()}
          className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10 h-7 w-7 rounded-full bg-background border shadow-md flex items-center justify-center hover:bg-muted transition-colors"
        >
          <ArrowDown className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Input area */}
      <div className="border-t px-3 py-2">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask about ${memberName}...`}
            rows={1}
            className="flex-1 resize-none rounded-lg bg-muted/50 px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground/50"
          />
          <Button
            size="sm"
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="h-8 w-8 p-0 rounded-lg shrink-0"
          >
            {sending ? <StopCircle className="h-4 w-4" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
