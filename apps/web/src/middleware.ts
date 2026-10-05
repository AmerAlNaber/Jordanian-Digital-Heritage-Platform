import createIntlMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";

import { routing } from "@/i18n/routing";

const intl = createIntlMiddleware(routing);
// ARK path: NAAN, then a NOID name (shoulder letters, one digit, extended digits). Only an
// optional page qualifier (/p12) may follow; the resolver receives the name and the record decides.
const ARK = /^\/ark:\/(\d{5,})\/([a-z]+\d[0-9bcdfghjkmnpqrstvwxz]+)(?=\/|$)/;
const ARK_QUALIFIER = /^\/?$|^\/p\d+\/?$/;

/**
 * Locale routing, the persistent identifier resolver and the per-request Content Security
 * Policy (SEC-16). Scripts run only with this request's nonce; nothing inline, nothing remote.
 */
export default function middleware(request: NextRequest) {
  const ark = ARK.exec(request.nextUrl.pathname);
  if (ark && ARK_QUALIFIER.test(request.nextUrl.pathname.slice(ark[0].length))) {
    const url = request.nextUrl.clone();
    url.pathname = `/${routing.defaultLocale}/resolve/${ark[2]}`;
    return NextResponse.redirect(url, 302);
  }

  const nonce = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64");
  const issuer = process.env.OIDC_ISSUER ?? "";
  const issuerOrigin = issuer ? new URL(issuer).origin : "";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    `form-action 'self' ${issuerOrigin}`.trim(),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
    "upgrade-insecure-requests",
  ].join("; ");

  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  const response = intl(new NextRequest(request, { headers }));
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("x-nonce", nonce);
  return response;
}

export const config = {
  matcher: [
    "/((?!api|health|_next|_vercel|favicon.ico|robots.txt|llms.txt|sitemap.xml|fonts|.*\\..*).*)",
    "/ark\\:/:path*",
  ],
};
