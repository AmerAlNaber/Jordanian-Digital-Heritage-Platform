import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

const NAME = /^[a-z0-9]{1,32}$/;

/** Mint the single-use download link (SEC-15). The file itself is fetched from the API directly. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ job: string }> }) {
  const { job } = await params;
  if (!NAME.test(job)) return new Response(null, { status: 404 });
  return proxyToApi(request, `/reader/prints/${job}/link`, { method: "POST" });
}
