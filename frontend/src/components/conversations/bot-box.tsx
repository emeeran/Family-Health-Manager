import { useState, useEffect, type KeyboardEvent } from "react";
import useSWR from "swr";
import { Bot, Send, StopCircle, Plus, User, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createConversation,
  sendMessageStream,
  sendMessage,
  type StreamEvent,
} from "@/lib/api/conversations";
import { listMembers } from "@/lib/api/members";
import type { MessageResponse, SendMessageResponse } from "@/lib/types/message";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { useBotBox } from "./bot-box-provider";
import { toast } from "sonner";
import {
  ChatMessage,
  StreamingMessage,
  useAutoResize,
  useScrollToBottom,
} from "@/components/shared/chat-primitives";
import { cn } from "@/lib/utils";

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
  const { isOpen, close, initialScope, initialMemberId } = useBotBox();
  const [scope, setScope] = useState<"general" | "member">("general");
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  const { data: membersData } = useSWR(isOpen ? "bot-box-members" : null, async () =>
    listMembers().catch(() => [])
  );
  const members: FamilyMemberResponse[] = membersData ?? [];

  const { endRef, scrollRef, scrollToBottom } = useScrollToBottom();
  const textareaRef = useAutoResize(input);

  /* Apply initial scope/memberId when the sheet opens */
  useEffect(() => {
    if (isOpen && initialScope) {
      setScope(initialScope);
      if (initialMemberId) {
        setSelectedMemberId(initialMemberId);
      }
      setConversationId(null);
      setMessages([]);
    }
  }, [isOpen, initialScope, initialMemberId]);

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

  function handleScopeChange(newScope: "general" | "member") {
    setScope(newScope);
    if (newScope === "general") {
      setSelectedMemberId(null);
    }
    setConversationId(null);
    setMessages([]);
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
          scope,
          family_member_id: scope === "member" ? selectedMemberId : null,
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

        {/* Scope toggle + member selector */}
        <div className="shrink-0 px-4 py-2 border-b border-border/40">
          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-full bg-muted/50 p-0.5">
              <button
                onClick={() => handleScopeChange("general")}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold rounded-full transition-all",
                  scope === "general"
                    ? "bg-card shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <MessageSquare className="h-2.5 w-2.5" />
                Public
              </button>
              <button
                onClick={() => handleScopeChange("member")}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold rounded-full transition-all",
                  scope === "member"
                    ? "bg-card shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <User className="h-2.5 w-2.5" />
                Private
              </button>
            </div>

            {scope === "member" && (
              <Select
                value={selectedMemberId ?? ""}
                onValueChange={(v) => {
                  setSelectedMemberId(v || null);
                  setConversationId(null);
                  setMessages([]);
                }}
              >
                <SelectTrigger className="w-28 h-6 text-[10px] rounded-full border-dashed">
                  <SelectValue placeholder="Pick member" />
                </SelectTrigger>
                <SelectContent>
                  {members.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.first_name} {m.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="relative flex-1 min-h-0">
          <div ref={scrollRef} className="absolute inset-0 overflow-y-auto scroll-smooth">
            {isEmpty ? (
              <div className="flex flex-col items-center justify-center h-full px-3 py-4 text-center">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted mb-2">
                  <Bot className="h-5 w-5 text-muted-foreground" />
                </div>
                <p className="text-xs text-muted-foreground max-w-[200px] mb-3">
                  {scope === "member" && !selectedMemberId
                    ? "Select a family member to start a private conversation."
                    : "Ask about health records, medications, or lab results."}
                </p>
                {!(scope === "member" && !selectedMemberId) && (
                  <div className="flex flex-col gap-1.5 w-full max-w-[260px]">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => {
                          setInput(s);
                          textareaRef.current?.focus();
                        }}
                        className="text-left text-[11px] leading-snug rounded-lg border border-border/50 bg-card/60 px-2.5 py-2 text-muted-foreground hover:bg-card hover:border-border hover:text-foreground/90 transition-all"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="px-3 py-3">
                {messages.map((msg, idx) => {
                  const showAvatar = idx === 0 || messages[idx - 1]?.role !== msg.role;
                  return (
                    <ChatMessage key={msg.id} msg={msg} variant="compact" showAvatar={showAvatar} />
                  );
                })}

                {/* Streaming */}
                {sending && <StreamingMessage content={streamingContent} variant="compact" />}
                <div ref={endRef} className="h-2" />
              </div>
            )}
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
              placeholder={
                scope === "member" && !selectedMemberId ? "Select a member first..." : "Message..."
              }
              aria-label="Type your message"
              disabled={sending || (scope === "member" && !selectedMemberId)}
              rows={1}
              className="flex-1 resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 max-h-28"
            />
            <Button
              onClick={handleSend}
              disabled={sending || !input.trim() || (scope === "member" && !selectedMemberId)}
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
