import type { NextRequest } from "next/server";

import { proxyToApi, readJson } from "@/lib/bff";

const NAME = /^[a-z0-9]{1,32}$/;

/** Ask for a print as the member; the grant token travels in its header (RDR-4). */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ session: string }> },
) {
  const { session } = await params;
  if (!NAME.test(session)) return new Response(null, { status: 404 });
  const body = await readJson(request);
  return proxyToApi(request, `/reader/sessions/${session}/print`, {
    method: "POST",
    body: body ?? {},
  });
}
