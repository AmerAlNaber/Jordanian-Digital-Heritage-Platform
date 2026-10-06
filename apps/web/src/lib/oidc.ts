// OpenID Connect relying party: Authorization Code with PKCE against Keycloak (SEC-1).
// Two clients: members (8 h sessions) and staff (1 h sessions), per the realm (SEC-2).
import * as client from "openid-client";

import { env } from "./env";

export type ClientKind = "web" | "staff";

const configs = new Map<ClientKind, Promise<client.Configuration>>();

export function callbackPath(kind: ClientKind): string {
  return kind === "staff" ? "/api/auth/callback/staff" : "/api/auth/callback";
}

/**
 * Fetches the provider metadata from the internal address and checks it names the public issuer.
 *
 * Behind the edge, Keycloak is reached as `keycloak:8080` but issues tokens for the public URL; its
 * discovery document carries the public issuer and front-channel endpoints, with back-channel
 * endpoints on the address that was asked (hostname-backchannel-dynamic). A plain discovery call
 * would refuse that document, because the issuer does not equal the address it came from.
 */
export async function discoverMetadata(
  internalIssuer: string,
  publicIssuer: string,
  fetchImpl: typeof fetch = fetch,
): Promise<client.ServerMetadata> {
  const url = `${internalIssuer.replace(/\/$/, "")}/.well-known/openid-configuration`;
  const response = await fetchImpl(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`OIDC discovery at ${url} answered ${response.status}`);
  const metadata = (await response.json()) as client.ServerMetadata;
  const expected = publicIssuer.replace(/\/$/, "");
  if (typeof metadata.issuer !== "string" || metadata.issuer.replace(/\/$/, "") !== expected) {
    throw new Error(
      `OIDC issuer mismatch: discovery names ${String(metadata.issuer)}, expected ${expected}`,
    );
  }
  return metadata;
}

export async function configuration(kind: ClientKind): Promise<client.Configuration> {
  let pending = configs.get(kind);
  if (!pending) {
    const id = kind === "staff" ? env("OIDC_STAFF_CLIENT_ID") : env("OIDC_WEB_CLIENT_ID");
    const secret =
      kind === "staff" ? env("OIDC_STAFF_CLIENT_SECRET") : env("OIDC_WEB_CLIENT_SECRET");
    const internal = env("OIDC_INTERNAL_ISSUER");
    pending = discoverMetadata(internal, env("OIDC_ISSUER")).then((metadata) => {
      const config = new client.Configuration(metadata, id, secret);
      if (new URL(internal).protocol === "http:") client.allowInsecureRequests(config);
      return config;
    });
    // A failed discovery must not be cached, or one unlucky start would stick.
    pending.catch(() => configs.delete(kind));
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
  extra: Record<string, string> = {},
) {
  const config = await configuration(kind);
  return client.buildAuthorizationUrl(config, {
    ...extra,
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

/**
 * The payload of a token the token endpoint just handed over, read without verifying it.
 *
 * Keycloak writes realm roles to the access token (the roles scope's default), not to the ID token,
 * so the session's roles have to be read here. The token arrived over the back channel from the
 * issuer's own endpoint, and it only shapes what the interface shows: the API verifies the
 * signature and decides every authorization itself.
 */
export function tokenPayload(token: string | undefined): Record<string, unknown> | undefined {
  const segment = token?.split(".")[1];
  if (!segment) return undefined;
  try {
    const parsed: unknown = JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

/** Realm roles from the ID token and the access token together, each one once. */
export function sessionRoles(
  idClaims: Record<string, unknown> | undefined,
  accessToken: string | undefined,
): string[] {
  return [
    ...new Set([...rolesFromClaims(idClaims), ...rolesFromClaims(tokenPayload(accessToken))]),
  ];
}
