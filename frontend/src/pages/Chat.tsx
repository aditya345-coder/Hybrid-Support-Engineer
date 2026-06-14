import { ChatMessages } from "../components/ChatMessages";
import { ChatInput } from "../components/ChatInput";
import { useChat } from "../hooks/useChat";

interface Props {
  sessionId: string;
  repoUrl?: string;
}

export function Chat({ sessionId, repoUrl }: Props) {
  const { messages, loading, send } = useChat(sessionId, repoUrl);

  return (
    <main className="flex-1 flex flex-col">
      <ChatMessages
        messages={messages}
        loading={loading}
        sessionId={sessionId}
        repoUrl={repoUrl}
      />
      <ChatInput onSend={send} disabled={loading} />
    </main>
  );
}
