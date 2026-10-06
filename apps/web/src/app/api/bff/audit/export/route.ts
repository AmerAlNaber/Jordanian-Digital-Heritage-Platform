import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/bff";

const SIGNATURE_HEADERS = [
  "content-disposition",
  "digest",
  "x-jdhp-signature",
  "x-jdhp-signature-key",
];

/** A signed audit export for a staff member; the signature headers travel with the file (ADM-5). */
export async function GET(request: NextRequest) {
  return proxyToApi(request, "/audit/export", {
    method: "GET",
    query: request.nextUrl.search.replace(/^\?/, ""),
    responseHeaders: SIGNATURE_HEADERS,
  });
}
