import type { SolveTicketResponse, PrepareRepoResponse } from "../types";
import type { StatusResponse } from "../types";
import { isAuthConfigured } from "../auth/config";
export type { StatusResponse };

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

let _getToken: (() => Promise<string | null>) | null = null;

export function setTokenGetter(getter: () => Promise<string | null>) {
  _getToken = getter;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!isAuthConfigured() || !_getToken) return {};
  try {
    const token = await _getToken();
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    // Token retrieval failed — proceed without auth header
  }
  return {};
}

export async function solveTicket(
  query: string,
  sessionId: string,
  repoUrl?: string,
  githubToken?: string,
  allowWebSearch = false
): Promise<SolveTicketResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Session-Id": sessionId,
    ...(await authHeaders()),
  };
  const res = await fetch(`${API_BASE}/v1/solve-ticket`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      user_query: query,
      session_id: sessionId,
      repo_url: repoUrl || null,
      allow_web_search: allowWebSearch,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function prepareRepo(
  repoUrl: string,
  sessionId: string,
  githubToken?: string
): Promise<PrepareRepoResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Session-Id": sessionId,
    ...(await authHeaders()),
  };
  const res = await fetch(`${API_BASE}/v1/prepare-repo`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      repo_url: repoUrl,
      session_id: sessionId,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function getStatus(sessionId: string): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/v1/status/${sessionId}`, {
    headers: {
      ...(await authHeaders()),
    },
  });
  return res.json();
}

export async function cleanupSession(sessionId: string): Promise<void> {
  const headers: Record<string, string> = {
    ...(await authHeaders()),
  };
  await fetch(`${API_BASE}/v1/cleanup/${sessionId}`, {
    method: "POST",
    headers,
  });
}

export async function submitFeedback(
  query: string,
  answer: string,
  featureDetected: string,
  thumbsUp: boolean,
  sessionId: string
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
  };
  await fetch(`${API_BASE}/v1/feedback`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      query,
      answer,
      feature_detected: featureDetected,
      thumbs_up: thumbsUp,
      session_id: sessionId,
    }),
  });
}
