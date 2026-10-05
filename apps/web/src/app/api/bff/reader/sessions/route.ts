import type { NextRequest } from "next/server";

import { proxyToApi, readJson } from "@/lib/bff";

/** Open a reader session as the signed-in member (or as a visitor on an Open work). */
export async function POST(request: NextRequest) {
  const body = await readJson(request);
  return proxyToApi(request, "/reader/sessions", { method: "POST", body: body ?? {} });
}
