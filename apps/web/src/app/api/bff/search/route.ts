import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

/** Search with the member's visibility, so the reader's in-book search sees the pages they may. */
export async function GET(request: NextRequest) {
  return proxyToApi(request, "/search", { method: "GET", query: request.nextUrl.search });
}
