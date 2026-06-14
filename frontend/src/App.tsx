import { useState } from "react";
import { useSession } from "./hooks/useSession";
import { Sidebar } from "./components/Sidebar";
import { Chat } from "./pages/Chat";
import { isAuthConfigured } from "./auth/config";
import { AuthGate } from "./auth/AuthGate";

function AppContent() {
  const sessionId = useSession();
  const [repoUrl, setRepoUrl] = useState<string>();

  return (
    <div className="flex h-screen">
      <Sidebar
        sessionId={sessionId}
        onRepoUrlChange={setRepoUrl}
      />
      <Chat
        sessionId={sessionId}
        repoUrl={repoUrl}
      />
    </div>
  );
}

export default function App() {
  if (isAuthConfigured()) {
    return (
      <AuthGate>
        <AppContent />
      </AuthGate>
    );
  }
  return <AppContent />;
}
