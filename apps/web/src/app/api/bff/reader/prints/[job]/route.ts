import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

const NAME = /^[a-z0-9]{1,32}$/;

export async function GET(request: NextRequest, { params }: { params: Promise<{ job: string }> }) {
  const { job } = await params;
  if (!NAME.test(job)) return new Response(null, { status: 404 });
  return proxyToApi(request, `/reader/prints/${job}`, { method: "GET" });
}
