"use client";

import { useEffect, useRef } from "react";
import mermaid from "mermaid";

interface Props {
  role: "user" | "assistant";
  content: string;
}

let mermaidInit = false;

export default function MessageBubble({ role, content }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mermaidInit) {
      mermaid.initialize({ startOnLoad: false, theme: "dark" });
      mermaidInit = true;
    }
    if (ref.current) {
      mermaid.run({ nodes: ref.current.querySelectorAll(".mermaid") as NodeListOf<HTMLElement> });
    }
  }, [content]);

  // Parse content: split by ```mermaid blocks
  const parts = parseMermaid(content);

  return (
    <div data-testid="message-bubble" data-role={role} className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        ref={ref}
        className={`max-w-2xl rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap
          ${role === "user"
            ? "bg-blue-600 text-white"
            : "bg-gray-800 text-gray-100"
          }`}
      >
        {parts.map((part, i) =>
          part.type === "text" ? (
            <span key={i}>{part.content}</span>
          ) : (
            <div key={i} className="my-3 p-3 bg-gray-900 rounded-xl overflow-x-auto">
              <div className="mermaid">{part.content}</div>
            </div>
          )
        )}
      </div>
    </div>
  );
}

function parseMermaid(text: string): Array<{ type: "text" | "mermaid"; content: string }> {
  const parts: Array<{ type: "text" | "mermaid"; content: string }> = [];
  const regex = /```mermaid\n([\s\S]*?)```/g;
  let last = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", content: text.slice(last, match.index) });
    }
    parts.push({ type: "mermaid", content: match[1].trim() });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ type: "text", content: text.slice(last) });
  }
  return parts;
}
