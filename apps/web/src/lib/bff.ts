// Backend-for-frontend calls (ADR-0002). The browser never holds the member's access token: these
// handlers add it server-side and pass the API's answer through, status and problem document alike.
import { type NextRequest, NextResponse } from "next/server";

import { env } from "./env";
import { currentSession } from "./session";

const PASSTHROUGH_HEADERS = ["x-jdhp-grant", "accept-language"];

export async function proxyToApi(
  request: NextRequest,
  path: string,
  { method, body, query }: { method: "GET" | "POST" | "DELETE"; body?: unknown; query?: string },
): Promise<NextResponse> {
  const session = await currentSession().catch(() => null);
  const url = new URL(path.replace(/^\//, ""), env("API_INTERNAL_URL").replace(/\/?$/, "/"));
  if (query) url.search = query;
  const headers = new Headers({ Accept: "application/json" });
  for (const name of PASSTHROUGH_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (session) headers.set("Authorization", `Bearer ${session.data.accessToken}`);
  const forwarded = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (forwarded) headers.set("X-Forwarded-For", forwarded);
  const agent = request.headers.get("user-agent");
  if (agent) headers.set("User-Agent", agent);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/json",
      "Cache-Control": "private, no-store",
    },
  });
}

export async function readJson(request: NextRequest): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return null;
  }
}
