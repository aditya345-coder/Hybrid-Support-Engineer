import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { UserMessage } from "./UserMessage";
import { BotMessage } from "./BotMessage";

interface Props {
  messages: Message[];
  loading: boolean;
  sessionId: string;
  repoUrl?: string;
}

export function ChatMessages({ messages, loading, sessionId, repoUrl }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        <p className="text-lg">Ask a question to get started</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.map((msg) =>
        msg.role === "user" ? (
          <UserMessage key={msg.id} content={msg.content} />
        ) : (
          <BotMessage
            key={msg.id}
            content={msg.content}
            query=""
            feature={msg.metadata?.detected_feature || "General"}
            sessionId={sessionId}
            repoUrl={repoUrl}
          />
        )
      )}
      {loading && (
        <div className="flex justify-start mb-4">
          <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2">
            <p className="text-sm text-gray-500">Thinking...</p>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
