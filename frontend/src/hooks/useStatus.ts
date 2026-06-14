import { useState, useEffect, useRef } from "react";
import { getStatus } from "../api/client";
import type { StatusResponse } from "../api/client";

export function useStatus(sessionId: string, enabled: boolean) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || !sessionId) return;

    const poll = async () => {
      try {
        const result = await getStatus(sessionId);
        setStatus(result);
        if (result.data?.stage === "complete" || result.data?.stage === "error") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    };

    poll();
    intervalRef.current = window.setInterval(poll, 2000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [sessionId, enabled]);

  return status;
}
