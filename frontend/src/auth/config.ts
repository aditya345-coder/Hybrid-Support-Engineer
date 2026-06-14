export const authConfig = {
  domain: import.meta.env.VITE_AUTH0_DOMAIN || "",
  clientId: import.meta.env.VITE_AUTH0_CLIENT_ID || "",
  audience: import.meta.env.VITE_AUTH0_AUDIENCE || "",
  scope: "openid profile email offline_access",
};

export const isAuthConfigured = (): boolean =>
  Boolean(authConfig.domain && authConfig.clientId);
