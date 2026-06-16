import { useEffect, useState, type ReactNode } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { setTokenGetter } from "../api/client";

interface Props {
  children: ReactNode;
}

export function AuthGate({ children }: Props) {
  const { getAccessTokenSilently, isAuthenticated, isLoading, loginWithRedirect } = useAuth0();
  const [authError, setAuthError] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState(false);

  useEffect(() => {
    setTokenGetter(async () => {
      if (!isAuthenticated) return null;
      try {
        setTokenError(false);
        return await getAccessTokenSilently();
      } catch (err) {
        console.error("[AuthGate] getAccessTokenSilently failed:", err);
        setTokenError(true);
        return null;
      }
    });
  }, [getAccessTokenSilently, isAuthenticated]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center space-y-3">
          <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto" />
          <p className="text-gray-500 text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center space-y-4 p-8">
          <h1 className="text-2xl font-bold text-gray-800">Support Engineer</h1>
          <p className="text-gray-500">Sign in to access the support assistant.</p>
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
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
          >
            Sign In
          </button>
          {authError && (
            <p className="text-red-600 text-sm mt-2 max-w-xs">{authError}</p>
          )}
        </div>
      </div>
    );
  }

  if (tokenError) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center space-y-4 p-8">
          <h1 className="text-2xl font-bold text-gray-800">Session Expired</h1>
          <p className="text-gray-500">Your session has expired. Please sign in again.</p>
          <button
            onClick={() => loginWithRedirect()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
          >
            Sign In Again
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
