import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

/** The public key that verifies audit exports and daily shipments (ADM-5, SEC-25). */
export async function GET(request: NextRequest) {
  return proxyToApi(request, "/audit/export/key", { method: "GET" });
}
