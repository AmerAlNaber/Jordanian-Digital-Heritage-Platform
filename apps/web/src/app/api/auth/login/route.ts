import { type NextRequest, NextResponse } from "next/server";

import { keycloakAction, uiLocale } from "@/lib/account-actions";
import { env, isProduction } from "@/lib/env";
import { authorizationUrl, callbackPath, preparePkce } from "@/lib/oidc";
import { encrypt } from "@/lib/session";

export const PKCE_COOKIE = "jdhp_auth";

function safeReturnPath(value: string | null): string {
  // Relative paths only (THREAT_MODEL T-F10).
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\"))
    return "/ar";
  return value;
}

export async function GET(request: NextRequest) {
  const kind = request.nextUrl.searchParams.get("staff") === "1" ? "staff" : "web";
  const returnTo = safeReturnPath(request.nextUrl.searchParams.get("return"));
  const pkce = await preparePkce();
  const redirectUri = `${env("NEXT_PUBLIC_BASE_URL")}${callbackPath(kind)}`;
  // Registration opens Keycloak's own form (ACC-1); an allowed `action` starts one of its
  // credential screens (ACC-2); anything else is ignored rather than forwarded.
  const extra: Record<string, string> = { ui_locales: uiLocale(returnTo) };
  if (request.nextUrl.searchParams.get("register") === "1" && kind === "web") {
    extra.prompt = "create";
  }
  // A fresh authentication, not the provider's session: a staff member who has just enrolled a
  // code signs in with it, so the token names the second factor (SEC-3).
  if (request.nextUrl.searchParams.get("reauth") === "1") extra.prompt = "login";
  const action = keycloakAction(request.nextUrl.searchParams.get("action"));
  if (action) extra.kc_action = action;
  const url = await authorizationUrl(kind, redirectUri, pkce, extra);
  const response = NextResponse.redirect(url);
  response.cookies.set(
    PKCE_COOKIE,
    encrypt(
      JSON.stringify({
        verifier: pkce.verifier,
        state: pkce.state,
        nonce: pkce.nonce,
        kind,
        returnTo,
        redirectUri,
      }),
    ),
    { httpOnly: true, secure: isProduction, sameSite: "lax", path: "/api/auth", maxAge: 600 },
  );
  return response;
}
