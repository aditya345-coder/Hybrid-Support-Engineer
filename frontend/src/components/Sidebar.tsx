import { useState, useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { prepareRepo, resumeRepo, freshRepo } from "../api/client";
import { useStatus } from "../hooks/useStatus";
import { isAuthConfigured } from "../auth/config";
import { ProgressBar } from "./ProgressBar";

interface Props {
  sessionId: string;
  onRepoUrlChange: (url: string) => void;
}

function AuthSection() {
  if (!isAuthConfigured()) return null;

  const { loginWithRedirect, logout, isAuthenticated, user } = useAuth0();
  const [authError, setAuthError] = useState<string | null>(null);

  if (!isAuthenticated) {
    return (
      <div>
        <button
          onClick={async () => {
            try {
              setAuthError(null);
              await loginWithRedirect();
            } catch (err) {
              setAuthError(
                err instanceof Error ? err.message : "Failed to sign in. Check Auth0 configuration."
              );
            }
          }}
          className="w-full py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-900 text-sm cursor-pointer"
        >
          Sign In
        </button>
        {authError && (
          <p className="text-red-600 text-xs mt-1">{authError}</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 pb-2 border-b">
      {user?.picture && (
        <img
          src={user.picture}
          alt=""
          className="w-8 h-8 rounded-full"
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{user?.name || user?.email || "User"}</p>
      </div>
      <button
        onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        className="text-xs text-gray-500 hover:text-gray-700 cursor-pointer"
      >
        Log out
      </button>
    </div>
  );
}

export function Sidebar({ sessionId, onRepoUrlChange }: Props) {
  const [repoUrl, setRepoUrl] = useState("");
  const [preparing, setPreparing] = useState(false);
  const [showResumeDialog, setShowResumeDialog] = useState(false);
  const [interruptedSession, setInterruptedSession] = useState<{ completed_phases: string[]; percent?: number } | null>(null);

  const status = useStatus(sessionId, preparing);

  // Fix preparing state bug: reset when stage completes or errors
  useEffect(() => {
    if (status?.data?.stage === "complete" || status?.data?.stage === "error") {
      setPreparing(false);
    }
  }, [status?.data?.stage]);

  const handlePrepare = async () => {
    if (!repoUrl.trim()) return;
    try {
      const result = await prepareRepo(repoUrl.trim(), sessionId);
      if (result.status === "interrupted") {
        setInterruptedSession({
          completed_phases: result.completed_phases || [],
        });
        setShowResumeDialog(true);
        return;
      }
      setPreparing(true);
    } catch {
      setPreparing(false);
    }
  };

  const handleResume = async () => {
    setShowResumeDialog(false);
    setPreparing(true);
    try {
      await resumeRepo(sessionId);
    } catch {
      setPreparing(false);
    }
  };

  const handleFresh = async () => {
    setShowResumeDialog(false);
    setPreparing(true);
    try {
      await freshRepo(repoUrl.trim(), sessionId);
    } catch {
      setPreparing(false);
    }
  };

  const handleRepoChange = (url: string) => {
    setRepoUrl(url);
    onRepoUrlChange(url);
  };

  const stage = status?.data?.stage;
  const isComplete = stage === "complete";
  const isError = stage === "error";

  return (
    <aside className="w-72 bg-gray-50 border-r p-4 flex flex-col gap-4">
      <AuthSection />

      <h2 className="font-semibold text-lg">Repository</h2>

      <div className="space-y-2">
        <label className="text-sm text-gray-600">Repo URL</label>
        <input
          type="text"
          value={repoUrl}
          onChange={(e) => handleRepoChange(e.target.value)}
          placeholder="owner/repo"
          disabled={preparing}
          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
      </div>

      <button
        onClick={handlePrepare}
        disabled={preparing || !repoUrl.trim()}
        className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 cursor-pointer"
      >
        {preparing ? "Preparing..." : "Prepare Repository"}
      </button>

      {showResumeDialog && interruptedSession && (
        <div className="p-3 border rounded-lg bg-yellow-50 text-sm">
          <p className="font-medium text-yellow-800">
            Previous session was interrupted
          </p>
          {interruptedSession.completed_phases.length > 0 && (
            <p className="text-yellow-700 text-xs mt-1">
              Completed: {interruptedSession.completed_phases.join(", ")}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <button
              onClick={handleResume}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm cursor-pointer"
            >
              Resume
            </button>
            <button
              onClick={handleFresh}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm cursor-pointer"
            >
              Start Fresh
            </button>
          </div>
        </div>
      )}

      {preparing && status?.data && (
        <ProgressBar
          percent={status.data.percent || 0}
          message={status.data.message || stage || "Processing..."}
          etaSeconds={status.data.eta_seconds}
        />
      )}

      <div className="mt-2">
        <span
          className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
            isComplete
              ? "bg-green-100 text-green-800"
              : isError
              ? "bg-red-100 text-red-800"
              : preparing
              ? "bg-blue-100 text-blue-800"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {isComplete ? "Ready" : isError ? "Error" : preparing ? "Processing" : "Not started"}
        </span>
      </div>
    </aside>
  );
}
