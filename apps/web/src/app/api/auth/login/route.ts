import { type NextRequest, NextResponse } from "next/server";

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
  const url = await authorizationUrl(kind, redirectUri, pkce);
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
