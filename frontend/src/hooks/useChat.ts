import { useState } from "react";
import { solveTicket } from "../api/client";
import type { Message } from "../types";

export function useChat(sessionId: string, repoUrl?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const send = async (query: string) => {
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: query };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const result = await solveTicket(query, sessionId, repoUrl);
      const botMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.answer || result.detail || "No response",
        metadata: result.metadata,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: err instanceof Error ? err.message : "Failed to reach the server. Is the backend running?",
      };
      setMessages((prev) => [...prev, errorMsg]);
    }

    setLoading(false);
  };

  return { messages, loading, send };
}
