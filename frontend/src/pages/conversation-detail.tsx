import {
  useState,
  useRef,
  useEffect,
  useCallback,
  lazy,
  Suspense,
  type KeyboardEvent,
} from "react";
import { useParams } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Send,
  Bot,
  User,
  ArrowDown,
  ArrowLeft,
  Copy,
  Check,
  StopCircle,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import { getConversation, sendMessage } from "@/lib/api/conversations";
import type { MessageResponse, SendMessageResponse } from "@/lib/types/message";
import type { ConversationDetailResponse } from "@/lib/types/conversation";

// Lazy-load markdown renderer + plugin together — ~150KB saved from initial chunk
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

/* ------------------------------------------------------------------ */
/*  Message actions                                                     */
/* ------------------------------------------------------------------ */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="rounded-md p-1 text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors"
      aria-label="Copy message"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Typing indicator                                                    */
/* ------------------------------------------------------------------ */

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-0.5">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Single message                                                      */
/* ------------------------------------------------------------------ */

function ChatMessage({
  msg,
  showAvatar,
  isLast: _isLast,
}: {
  msg: MessageResponse;
  showAvatar: boolean;
  isLast: boolean;
}) {
  const isUser = msg.role === "user";
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className={`group flex gap-3 ${isUser ? "flex-row-reverse" : ""} ${showAvatar ? "mt-6" : "mt-0.5"}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Avatar */}
      <div className={`shrink-0 mt-0.5 ${showAvatar ? "" : "invisible"}`}>
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold select-none ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300"
          }`}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
      </div>

      {/* Bubble + meta */}
      <div
        className={`max-w-[78%] min-w-0 space-y-1 ${isUser ? "items-end" : "items-start"} flex flex-col`}
      >
        {/* Sender + time label */}
        {showAvatar && (
          <div className={`flex items-center gap-2 px-1 ${isUser ? "flex-row-reverse" : ""}`}>
            <span className="text-xs font-medium text-foreground">
              {isUser ? "You" : "Health AI"}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {new Date(msg.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        )}

        {/* Content bubble */}
        <div className="relative">
          <div
            className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              isUser
                ? "bg-primary text-primary-foreground rounded-tr-md"
                : "bg-muted/80 rounded-tl-md"
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

          {/* Action buttons (visible on hover) */}
          {!isUser && hovered && (
            <div className="absolute -bottom-7 left-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <CopyButton text={msg.content} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Date separator                                                      */
/* ------------------------------------------------------------------ */

function DateSeparator({ date }: { date: string }) {
  const label = (() => {
    const d = new Date(date + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
    if (diff === 0) return "Today";
    if (diff === 1) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  })();

  return (
    <div className="flex items-center gap-3 my-4">
      <div className="flex-1 h-px bg-border" />
      <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                           */
/* ------------------------------------------------------------------ */

export default function ConversationDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    chatEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  // Load conversation via SWR — caches across navigations
  const {
    data: convData,
    isLoading: loading,
    error,
    mutate,
  } = useSWR(
    conversationId ? `conversation-${conversationId}` : null,
    async () => {
      const data: ConversationDetailResponse = await getConversation(conversationId!);
      return data;
    },
    { revalidateOnFocus: false, dedupingInterval: 30_000 }
  );

  // Sync SWR data to local messages state
  useEffect(() => {
    if (convData) {
      setMessages(convData.messages);
    }
  }, [convData]);

  const title = convData?.conversation.title || "Chat";

  // Auto-scroll on new messages
  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

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
  }, [loading]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [input]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending || !conversationId) return;
    setSending(true);
    setInput("");

    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    try {
      const response: SendMessageResponse = await sendMessage(conversationId, {
        content: text,
      });
      setMessages((prev) => [...prev, response.user_message, response.assistant_message]);
    } catch {
      toast.error("Failed to send message");
      setInput(text); // Restore input on error
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter to send, Shift+Enter for newline
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // Compute date groups
  function getMessageDate(msg: MessageResponse) {
    return new Date(msg.created_at).toISOString().slice(0, 10);
  }

  /* ---- Loading skeleton ---- */
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <AlertCircle className="h-10 w-10 text-destructive mb-3" />
        <p className="text-sm text-muted-foreground">Failed to load conversation</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => mutate()}>
          Retry
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col h-[calc(100vh-6rem)]">
        <div className="flex items-center gap-3 px-2 py-3 border-b shrink-0">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="space-y-1.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
        <div className="flex-1 p-6 space-y-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className={`flex gap-3 ${i % 2 === 0 ? "flex-row-reverse" : ""}`}>
              <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
              <div className="space-y-1.5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className={`h-16 rounded-2xl ${i % 2 === 0 ? "w-48" : "w-72"}`} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  /* ---- Main chat view ---- */
  return (
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      {/* ── Header bar ── */}
      <div className="flex items-center gap-3 px-3 py-2.5 border-b bg-background shrink-0">
        <button
          onClick={() => navigate("/conversations")}
          className="flex md:hidden items-center justify-center h-8 w-8 rounded-lg hover:bg-muted transition-colors"
          aria-label="Back to conversations"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20">
            <Bot className="h-4.5 w-4.5 text-violet-600 dark:text-violet-400" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold truncate">{title}</h2>
            <p className="text-[11px] text-muted-foreground">
              {messages.length} message{messages.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
      </div>

      {/* ── Message area ── */}
      <div className="relative flex-1 min-h-0">
        <div ref={scrollRef} className="absolute inset-0 overflow-y-auto scroll-smooth">
          <div className="mx-auto max-w-3xl px-4 py-5">
            {/* Empty state */}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 mb-4">
                  <Bot className="h-7 w-7 text-violet-600 dark:text-violet-400" />
                </div>
                <h3 className="text-base font-semibold mb-1">Health AI Assistant</h3>
                <p className="text-sm text-muted-foreground max-w-xs">
                  Ask questions about health records, medications, lab results, or general health
                  topics.
                </p>
              </div>
            )}

            {/* Messages */}
            {messages.map((msg, idx) => {
              const _isUser = msg.role === "user";
              const showAvatar = idx === 0 || messages[idx - 1]?.role !== msg.role;
              const showDate =
                idx === 0 || getMessageDate(msg) !== getMessageDate(messages[idx - 1]);
              const isLast = idx === messages.length - 1;

              return (
                <div key={msg.id}>
                  {showDate && <DateSeparator date={getMessageDate(msg)} />}
                  <ChatMessage msg={msg} showAvatar={showAvatar} isLast={isLast} />
                </div>
              );
            })}

            {/* Typing indicator */}
            {sending && (
              <div className="flex gap-3 mt-6">
                <div className="shrink-0 mt-0.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/20 to-blue-500/20 text-violet-700 dark:text-violet-300">
                    <Bot className="h-4 w-4" />
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 px-1">
                    <span className="text-xs font-medium text-foreground">Health AI</span>
                  </div>
                  <div className="bg-muted/80 rounded-2xl rounded-tl-md px-4 py-3">
                    <TypingIndicator />
                  </div>
                </div>
              </div>
            )}

            <div ref={chatEndRef} className="h-4" />
          </div>
        </div>

        {/* Scroll-to-bottom */}
        {showScrollBtn && (
          <button
            onClick={() => scrollToBottom()}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 flex h-9 w-9 items-center justify-center rounded-full border bg-background/90 backdrop-blur-sm shadow-lg hover:bg-muted transition-colors z-10"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* ── Input bar ── */}
      <div className="shrink-0 border-t bg-background px-3 py-3">
        <div className="mx-auto max-w-3xl flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Health AI..."
              disabled={sending}
              rows={1}
              className="w-full resize-none rounded-xl border border-input bg-transparent px-4 py-2.5 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 max-h-40"
            />
          </div>
          <Button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            size="icon"
            className="h-10 w-10 shrink-0 rounded-xl"
          >
            {sending ? (
              <StopCircle className="h-4 w-4 animate-pulse" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="mx-auto max-w-3xl text-center mt-1.5 text-[10px] text-muted-foreground/60">
          Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
