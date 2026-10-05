import type { NextRequest } from "next/server";

import { proxyToApi, readJson } from "@/lib/bff";

/** Ask for a phone verification code as the signed-in member (ACC-1). */
export async function POST(request: NextRequest) {
  const body = await readJson(request);
  return proxyToApi(request, "/me/phone", { method: "POST", body: body ?? {} });
}
