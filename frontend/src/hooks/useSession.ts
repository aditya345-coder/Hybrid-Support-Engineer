import { useState, useEffect } from "react";

function generateId(): string {
  return "ui_" + Math.random().toString(36).substring(2, 15);
}

export function useSession() {
  const [sessionId, setSessionIdState] = useState<string>("");

  useEffect(() => {
    let id = localStorage.getItem("session_id");
    if (!id) {
      id = generateId();
      localStorage.setItem("session_id", id);
    }
    setSessionIdState(id);
  }, []);

  const setSessionId = (id: string) => {
    localStorage.setItem("session_id", id);
    setSessionIdState(id);
  };

  return { sessionId, setSessionId };
}
