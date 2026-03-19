"use client";

import { useState, useRef, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import MessageBubble from "@/components/MessageBubble";
import ProgressBar from "@/components/ProgressBar";
import BusinessCanvas from "@/components/BusinessCanvas";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface BMCProgress {
  covered_count: number;
  total: number;
  missing_items: string[];
  current_stage: string;
}

export default function Home() {
  const [sessionId] = useState(() => uuidv4());
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "你好！我是 **TokenFounder**，专门帮助你孵化 AI Agent 创业想法 🚀\n\n" +
        "我们将一起经历 Design Thinking 的五个阶段：**共情 → 定义 → 构想 → 原型 → 验证**，最终生成一份完整的商业画布。\n\n" +
        "先告诉我：**你在日常生活或工作中，观察到哪个场景让人觉得「这件事太低效了，应该能自动化」？**",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState<BMCProgress | null>(null);
  const [canvas, setCanvas] = useState<Record<string, unknown> | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: userMessage }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let assistantText = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const raw = decoder.decode(value);
        for (const line of raw.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));

          if (event.type === "text") {
            assistantText += event.data.chunk;
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: assistantText,
              };
              return updated;
            });
          } else if (event.type === "redirect") {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: event.data.message,
              };
              return updated;
            });
          } else if (event.type === "bmc_progress") {
            setProgress(event.data);
          } else if (event.type === "canvas_start") {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: event.data.message },
            ]);
          } else if (event.type === "canvas_complete") {
            setCanvas(event.data);
          }
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const stageLabels: Record<string, string> = {
    Empathize: "共情 · 挖掘痛点",
    Define: "定义 · 聚焦问题",
    Ideate: "构想 · Agent方案",
    Prototype: "原型 · 商业模式",
    Validate: "验证 · 市场数据",
    Complete: "完成 · 画布生成",
  };

  return (
    <main className="flex flex-col h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <div>
          <h1 className="text-xl font-bold text-white">TokenFounder</h1>
          <p className="text-xs text-gray-400">AI Agent 创业想法孵化器</p>
        </div>
        {progress && (
          <div className="text-sm text-gray-400">
            阶段：
            <span className="text-blue-400 font-medium">
              {stageLabels[progress.current_stage] || progress.current_stage}
            </span>
          </div>
        )}
      </header>

      {/* Progress bar */}
      {progress && (
        <ProgressBar
          covered={progress.covered_count}
          total={progress.total}
          missing={progress.missing_items}
        />
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg, i) => (
          <MessageBubble key={i} role={msg.role} content={msg.content} />
        ))}
        {isLoading && (
          <div className="flex items-center gap-2 text-gray-500 text-sm pl-2">
            <span className="animate-pulse">●●●</span>
            <span>TokenFounder 正在思考...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Business Canvas Modal */}
      {canvas && (
        <BusinessCanvas
          data={canvas as Parameters<typeof BusinessCanvas>[0]["data"]}
          onClose={() => setCanvas(null)}
        />
      )}

      {/* Input */}
      <div className="px-4 py-4 border-t border-gray-800">
        <div className="flex gap-3 max-w-4xl mx-auto">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="分享你的想法... (Enter发送，Shift+Enter换行)"
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:border-blue-500 transition-colors"
            rows={2}
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
            className="px-5 py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-sm font-medium transition-colors"
          >
            发送
          </button>
        </div>
      </div>
    </main>
  );
}
