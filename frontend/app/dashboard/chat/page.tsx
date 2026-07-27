"use client";

import { useState, useRef, useEffect } from "react";
import { createClient } from "@/lib/supabase";
import { queryDocuments } from "@/lib/api";
import clsx from "clsx";

interface Source {
  original_name: string;
  document_id: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  was_confident?: boolean;
  latency_ms?: number;
  loading?: boolean;
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div className={clsx("flex gap-3 animate-slide-up", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div className={clsx(
        "w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-bold",
        isUser
          ? "bg-brand-500/20 border border-brand-500/30 text-brand-300"
          : "bg-surface-elevated border border-surface-border text-gray-400"
      )}>
        {isUser ? "You" : "AI"}
      </div>

      {/* Bubble */}
      <div className={clsx(
        "max-w-[75%] rounded-2xl px-5 py-3.5 text-sm leading-relaxed",
        isUser
          ? "bg-brand-500/20 border border-brand-500/25 text-white rounded-tr-sm"
          : "bg-surface-card border border-surface-border text-gray-100 rounded-tl-sm"
      )}>
        {msg.loading ? (
          <div className="flex gap-1.5 items-center py-1">
            <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        ) : (
          <>
            <p className="whitespace-pre-wrap">{msg.content}</p>

            {/* Sources */}
            {msg.sources && msg.sources.length > 0 && msg.was_confident && (
              <div className="mt-3 pt-3 border-t border-surface-border">
                <p className="text-gray-500 text-xs font-medium mb-2">Sources</p>
                <div className="flex flex-wrap gap-2">
                  {msg.sources.map((s) => (
                    <span key={s.document_id}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                                     bg-surface-elevated border border-surface-border text-xs text-gray-300">
                      <svg className="w-3 h-3 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      {s.original_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Latency */}
            {msg.latency_ms && (
              <p className="text-gray-600 text-xs mt-2">{msg.latency_ms}ms</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "👋 Hi! Ask me anything about your company's policies, SOPs, or onboarding guides. I'll answer based on your uploaded documents.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(question: string) {
    if (!token || !question.trim() || loading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: question };
    const loadingMsg: Message = { id: "loading", role: "assistant", content: "", loading: true };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setLoading(true);

    try {
      const result = await queryDocuments(question, token);
      const assistantMsg: Message = {
        id: `${Date.now()}-ai`,
        role: "assistant",
        content: result.answer,
        sources: result.sources,
        was_confident: result.was_answered_confidently,
        latency_ms: result.latency_ms,
      };
      setMessages((prev) => prev.filter((m) => m.id !== "loading").concat(assistantMsg));
    } catch (err: unknown) {
      const errorMsg: Message = {
        id: `${Date.now()}-err`,
        role: "assistant",
        content: err instanceof Error ? `Error: ${err.message}` : "Something went wrong. Please try again.",
      };
      setMessages((prev) => prev.filter((m) => m.id !== "loading").concat(errorMsg));
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  const SUGGESTED = [
    "What is the remote work policy?",
    "How many vacation days do employees get?",
    "What's the onboarding process for new hires?",
  ];

  return (
    <div className="flex flex-col h-screen max-h-screen">
      {/* Header */}
      <div className="px-8 py-5 border-b border-surface-border bg-surface-card shrink-0">
        <h1 className="text-lg font-bold text-white">Ask a Question</h1>
        <p className="text-gray-400 text-sm mt-0.5">AI-powered answers grounded in your company documents</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {/* Suggested questions (only when no real messages) */}
        {messages.length === 1 && (
          <div className="space-y-2 animate-fade-in">
            <p className="text-gray-500 text-xs font-medium">Suggested questions</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED.map((q) => (
                <button
                  key={q}
                  id={`suggested-${q.slice(0, 20).replace(/\s+/g, "-").toLowerCase()}`}
                  onClick={() => sendMessage(q)}
                  className="px-3 py-2 rounded-xl border border-surface-border bg-surface-card
                             text-gray-300 text-sm hover:border-brand-500/50 hover:text-white
                             hover:bg-surface-elevated transition-all duration-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-8 py-5 border-t border-surface-border bg-surface-card shrink-0">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            id="chat-input"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about vacation policy, onboarding steps, expense process…"
            disabled={loading}
            className="input resize-none min-h-[48px] max-h-[140px] leading-relaxed"
            style={{ height: "auto" }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
            }}
          />
          <button
            id="chat-send-btn"
            onClick={() => sendMessage(input)}
            disabled={loading || !input.trim()}
            className="btn-primary h-12 w-12 rounded-xl p-0 flex items-center justify-center shrink-0"
          >
            {loading ? (
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-gray-600 text-xs mt-2">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}
