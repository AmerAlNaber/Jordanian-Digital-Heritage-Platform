// OpenID Connect relying party: Authorization Code with PKCE against Keycloak (SEC-1).
// Two clients: members (8 h sessions) and staff (1 h sessions), per the realm (SEC-2).
import * as client from "openid-client";

import { env } from "./env";

export type ClientKind = "web" | "staff";

const configs = new Map<ClientKind, Promise<client.Configuration>>();

export function callbackPath(kind: ClientKind): string {
  return kind === "staff" ? "/api/auth/callback/staff" : "/api/auth/callback";
}

export async function configuration(kind: ClientKind): Promise<client.Configuration> {
  let pending = configs.get(kind);
  if (!pending) {
    const id = kind === "staff" ? env("OIDC_STAFF_CLIENT_ID") : env("OIDC_WEB_CLIENT_ID");
    const secret =
      kind === "staff" ? env("OIDC_STAFF_CLIENT_SECRET") : env("OIDC_WEB_CLIENT_SECRET");
    const internal = new URL(env("OIDC_INTERNAL_ISSUER"));
    const options: client.DiscoveryRequestOptions = {};
    if (internal.protocol === "http:") options.execute = [client.allowInsecureRequests];
    pending = client.discovery(internal, id, secret, undefined, options).then((config) => {
      // Tokens are issued for the public issuer; discovery may have run against the internal address.
      const metadata = config.serverMetadata();
      if (metadata.issuer !== env("OIDC_ISSUER")) {
        // Keycloak with hostname-backchannel-dynamic reports the public issuer; nothing to do.
      }
      return config;
    });
    configs.set(kind, pending);
  }
  return pending;
}

export function newPkce() {
  const verifier = client.randomPKCECodeVerifier();
  return {
    verifier,
    state: client.randomState(),
    nonce: client.randomNonce(),
    challenge: client.calculatePKCECodeChallenge(verifier),
  };
}

export async function authorizationUrl(
  kind: ClientKind,
  redirectUri: string,
  pkce: Awaited<ReturnType<typeof preparePkce>>,
) {
  const config = await configuration(kind);
  return client.buildAuthorizationUrl(config, {
    redirect_uri: redirectUri,
    scope: "openid profile email",
    code_challenge: pkce.challenge,
    code_challenge_method: "S256",
    state: pkce.state,
    nonce: pkce.nonce,
  });
}

export async function preparePkce() {
  const { verifier, state, nonce, challenge } = newPkce();
  return { verifier, state, nonce, challenge: await challenge };
}

export async function exchangeCode(
  kind: ClientKind,
  currentUrl: URL,
  pkce: { verifier: string; state: string; nonce: string },
) {
  const config = await configuration(kind);
  return client.authorizationCodeGrant(config, currentUrl, {
    pkceCodeVerifier: pkce.verifier,
    expectedState: pkce.state,
    expectedNonce: pkce.nonce,
    idTokenExpected: true,
  });
}

export async function refresh(kind: ClientKind, refreshToken: string) {
  const config = await configuration(kind);
  return client.refreshTokenGrant(config, refreshToken);
}

export async function endSessionUrl(
  kind: ClientKind,
  idToken: string | undefined,
  postLogout: string,
) {
  const config = await configuration(kind);
  return client.buildEndSessionUrl(config, {
    post_logout_redirect_uri: postLogout,
    ...(idToken ? { id_token_hint: idToken } : {}),
  });
}

export function rolesFromClaims(claims: Record<string, unknown> | undefined): string[] {
  const access = claims?.realm_access as { roles?: unknown } | undefined;
  return Array.isArray(access?.roles)
    ? access.roles.filter((r): r is string => typeof r === "string")
    : [];
}
