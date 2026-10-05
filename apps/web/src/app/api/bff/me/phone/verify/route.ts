import type { NextRequest } from "next/server";

import { proxyToApi, readJson } from "@/lib/bff";

/** Confirm the phone verification code (ACC-1). */
export async function POST(request: NextRequest) {
  const body = await readJson(request);
  return proxyToApi(request, "/me/phone/verify", { method: "POST", body: body ?? {} });
}
