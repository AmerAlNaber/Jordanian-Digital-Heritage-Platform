import { type NextRequest, NextResponse } from "next/server";

import { env, isProduction } from "./env";
import { type ClientKind, exchangeCode, sessionRoles } from "./oidc";
import {
  SESSION_COOKIE,
  cookieOptions,
  createSession,
  decrypt,
  encodeCookie,
  ttlFor,
} from "./session";

const PKCE_COOKIE = "jdhp_auth";

type Pending = {
  verifier: string;
  state: string;
  nonce: string;
  kind: ClientKind;
  returnTo: string;
  redirectUri: string;
};

/** Shared by /api/auth/callback and /api/auth/callback/staff: code exchange, then a server-side session. */
export async function handleCallback(request: NextRequest, expectedKind: ClientKind) {
  const base = env("NEXT_PUBLIC_BASE_URL");
  const raw = request.cookies.get(PKCE_COOKIE)?.value;
  if (!raw) return NextResponse.redirect(new URL("/ar?auth=expired", base));
  let pending: Pending;
  try {
    pending = JSON.parse(decrypt(raw)) as Pending;
  } catch {
    return NextResponse.redirect(new URL("/ar?auth=invalid", base));
  }
  if (pending.kind !== expectedKind)
    return NextResponse.redirect(new URL("/ar?auth=invalid", base));

  // The provider redirected to the public URL; rebuild it from the registered redirect URI so the
  // exchange validates the exact callback the realm knows.
  const currentUrl = new URL(pending.redirectUri);
  currentUrl.search = request.nextUrl.search;
  const tokens = await exchangeCode(pending.kind, currentUrl, pending);
  const claims = tokens.claims();
  if (!claims || !tokens.access_token)
    return NextResponse.redirect(new URL("/ar?auth=failed", base));

  const id = await createSession({
    client: pending.kind,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
    expiresAt: Date.now() + (tokens.expiresIn() ?? 600) * 1000,
    subject: String(claims.sub),
    roles: sessionRoles(claims as Record<string, unknown>, tokens.access_token),
    name: typeof claims.name === "string" ? claims.name : undefined,
    createdAt: Date.now(),
  });
  const response = NextResponse.redirect(new URL(pending.returnTo, base));
  response.cookies.set(SESSION_COOKIE, encodeCookie(id), cookieOptions(ttlFor(pending.kind)));
  response.cookies.set(PKCE_COOKIE, "", {
    ...cookieOptions(0),
    path: "/api/auth",
    secure: isProduction,
  });
  return response;
}
