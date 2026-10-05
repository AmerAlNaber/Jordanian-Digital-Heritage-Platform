import type { ReaderSessionSummary } from "@jdhp/schemas";

import { env } from "./env";

/**
 * The member's sign-ins (identity provider sessions) and the readers open under each (SEC-5).
 *
 * Sign-ins come from Keycloak's Account REST API with the member's own token, which carries the
 * `account` audience for this purpose (ADR-0009). Readers come from the platform API.
 */

export type KeycloakSession = {
  id: string;
  ipAddress?: string;
  started?: number;
  lastAccess?: number;
  expires?: number;
  browser?: string;
  current?: boolean;
  clients?: { clientId: string; clientName?: string }[];
};

export type SignInView = {
  id: string | null;
  current: boolean;
  browser: string | null;
  ipAddress: string | null;
  startedAt: string | null;
  lastAccessAt: string | null;
  readers: ReaderSessionSummary[];
};

function accountUrl(path: string): string {
  return `${env("OIDC_INTERNAL_ISSUER").replace(/\/$/, "")}/account${path}`;
}

export async function listSignIns(accessToken: string): Promise<KeycloakSession[]> {
  const response = await fetch(accountUrl("/sessions"), {
    headers: { Accept: "application/json", Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) return [];
  const body: unknown = await response.json();
  return Array.isArray(body) ? (body as KeycloakSession[]) : [];
}

/** Ends one sign-in at the identity provider; true when it is gone (or was already). */
export async function endSignIn(accessToken: string, id: string): Promise<boolean> {
  const response = await fetch(accountUrl(`/sessions/${encodeURIComponent(id)}`), {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  return response.ok || response.status === 404;
}

/** The `sid` claim of the member's own access token: no verification needed, it is ours. */
export function currentSid(accessToken: string): string | null {
  const payload = accessToken.split(".")[1];
  if (!payload) return null;
  try {
    const json = Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString(
      "utf8",
    );
    const claims: unknown = JSON.parse(json);
    if (claims && typeof claims === "object" && "sid" in claims) {
      const sid = (claims as { sid?: unknown }).sid;
      return typeof sid === "string" && sid ? sid : null;
    }
  } catch {
    return null;
  }
  return null;
}

function iso(seconds: number | undefined): string | null {
  return typeof seconds === "number" && seconds > 0 ? new Date(seconds * 1000).toISOString() : null;
}

/** Group readers under their sign-in; readers whose sign-in Keycloak no longer lists go last. */
export function mergeSignIns(
  signIns: KeycloakSession[],
  readers: ReaderSessionSummary[],
  current: string | null,
): SignInView[] {
  const byId = new Map<string, SignInView>();
  for (const signIn of signIns) {
    byId.set(signIn.id, {
      id: signIn.id,
      current: signIn.current === true || signIn.id === current,
      browser: signIn.browser ?? null,
      ipAddress: signIn.ipAddress ?? null,
      startedAt: iso(signIn.started),
      lastAccessAt: iso(signIn.lastAccess),
      readers: [],
    });
  }
  const orphans: ReaderSessionSummary[] = [];
  for (const reader of readers) {
    const owner = reader.sign_in ? byId.get(reader.sign_in) : undefined;
    if (owner) owner.readers.push(reader);
    else orphans.push(reader);
  }
  const views = [...byId.values()].sort((a, b) => Number(b.current) - Number(a.current));
  if (orphans.length > 0) {
    views.push({
      id: null,
      current: false,
      browser: null,
      ipAddress: null,
      startedAt: null,
      lastAccessAt: null,
      readers: orphans,
    });
  }
  return views;
}
