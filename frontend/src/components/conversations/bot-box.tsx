import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Bot, Send, StopCircle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  createConversation,
  sendMessageStream,
  sendMessage,
  type StreamEvent,
} from "@/lib/api/conversations";
import type { MessageResponse, SendMessageResponse } from "@/lib/types/message";
import { useBotBox } from "./bot-box-provider";
import { toast } from "sonner";
import {
  ChatMessage,
  StreamingMessage,
  useAutoResize,
  useScrollToBottom,
} from "@/components/shared/chat-primitives";

/* ------------------------------------------------------------------ */
/*  Suggestion chips                                                    */
/* ------------------------------------------------------------------ */

const SUGGESTIONS = [
  "Summarize my family's recent health activity",
  "What medications is my family currently taking?",
  "Any overdue health reminders?",
];

/* ------------------------------------------------------------------ */
/*  BotBox                                                              */
/* ------------------------------------------------------------------ */

export function BotBox() {
  const { isOpen, close } = useBotBox();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  const { endRef, scrollRef, scrollToBottom } = useScrollToBottom();
  const textareaRef = useAutoResize(input);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, streamingContent, scrollToBottom]);

  function startNewChat() {
    setConversationId(null);
    setMessages([]);
    setInput("");
    setStreamingContent("");
    textareaRef.current?.focus();
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;

    setSending(true);
    setStreamingContent("");
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    let activeConvId = conversationId;

    if (!activeConvId) {
      try {
        const conv = await createConversation({
          scope: "general",
          family_member_id: null,
          title: text.slice(0, 60),
        });
        activeConvId = conv.id;
        setConversationId(conv.id);
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
    <Sheet
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-md p-0 flex flex-col"
        showCloseButton={false}
      >
        {/* Header */}
        <SheetHeader className="flex-row items-center justify-between border-b px-4 py-3 space-y-0">
          <div>
            <SheetTitle className="text-sm">AI Assistant</SheetTitle>
            <SheetDescription className="text-xs">Quick health Q&A</SheetDescription>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={startNewChat} aria-label="New chat">
            <Plus className="h-4 w-4" />
          </Button>
        </SheetHeader>

        {/* Messages */}
        <div className="relative flex-1 min-h-0">
          <div ref={scrollRef} className="absolute inset-0 overflow-y-auto scroll-smooth">
            <div className="px-3 py-3">
              {isEmpty ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted mb-2">
                    <Bot className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <p className="text-xs text-muted-foreground max-w-[200px] mb-3">
                    Ask about health records, medications, or lab results.
                  </p>
                  <div className="flex flex-col gap-1 w-full">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => {
                          setInput(s);
                          textareaRef.current?.focus();
                        }}
                        className="text-left text-xs rounded-md border px-2.5 py-1.5 text-muted-foreground hover:bg-muted/50 transition-colors"
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
                    return (
                      <ChatMessage
                        key={msg.id}
                        msg={msg}
                        variant="compact"
                        showAvatar={showAvatar}
                      />
                    );
                  })}

                  {/* Streaming */}
                  {sending && <StreamingMessage content={streamingContent} variant="compact" />}
                </>
              )}
              <div ref={endRef} className="h-2" />
            </div>
          </div>
        </div>

        {/* Input */}
        <div className="shrink-0 border-t px-3 py-2">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message..."
              aria-label="Type your message"
              disabled={sending}
              rows={1}
              className="flex-1 resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 max-h-28"
            />
            <Button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              size="icon"
              className="h-8 w-8 shrink-0 rounded-lg"
            >
              {sending ? (
                <StopCircle className="h-4 w-4 animate-pulse" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
