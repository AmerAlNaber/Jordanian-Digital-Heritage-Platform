import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

/** End one of the member's own readers (SEC-5). */
export async function DELETE(request: NextRequest, context: { params: Promise<{ name: string }> }) {
  const { name } = await context.params;
  return proxyToApi(request, `/me/sessions/${encodeURIComponent(name)}`, { method: "DELETE" });
}
