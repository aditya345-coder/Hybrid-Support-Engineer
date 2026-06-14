import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import App from "./App";
import { authConfig, isAuthConfigured } from "./auth/config";
import "./index.css";

const root = createRoot(document.getElementById("root")!);

if (isAuthConfigured()) {
  root.render(
    <StrictMode>
      <Auth0Provider
        domain={authConfig.domain}
        clientId={authConfig.clientId}
        authorizationParams={{
          redirect_uri: window.location.origin,
          audience: authConfig.audience || undefined,
          scope: authConfig.scope,
        }}
        cacheLocation="localstorage"
        useRefreshTokens={true}
      >
        <App />
      </Auth0Provider>
    </StrictMode>
  );
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}
