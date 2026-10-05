import type { NextRequest } from "next/server";

import { handleCallback } from "@/lib/callback";

export async function GET(request: NextRequest) {
  return handleCallback(request, "staff");
}
