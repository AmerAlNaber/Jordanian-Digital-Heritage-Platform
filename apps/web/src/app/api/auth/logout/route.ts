import { type NextRequest, NextResponse } from "next/server";

import { env } from "@/lib/env";
import { endSessionUrl } from "@/lib/oidc";
import {
  SESSION_COOKIE,
  cookieOptions,
  decodeCookie,
  destroySession,
  readSession,
} from "@/lib/session";

export async function POST(request: NextRequest) {
  const base = env("NEXT_PUBLIC_BASE_URL");
  const id = decodeCookie(request.cookies.get(SESSION_COOKIE)?.value);
  let target = new URL("/ar", base);
  if (id) {
    const data = await readSession(id);
    await destroySession(id);
    if (data) {
      try {
        target = await endSessionUrl(data.client, data.idToken, `${base}/ar`);
      } catch {
        target = new URL("/ar", base);
      }
    }
  }
  const response = NextResponse.redirect(target, 303);
  response.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return response;
}
