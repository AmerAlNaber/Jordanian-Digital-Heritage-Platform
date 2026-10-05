import { type NextRequest, NextResponse } from "next/server";

import { proxyToApi } from "@/lib/bff";
import { currentSession } from "@/lib/session";
import { endSignIn } from "@/lib/sign-ins";

/**
 * End a sign-in: at the identity provider with the member's own token, then every reader it
 * opened through the platform API (SEC-5). The member's current sign-in may be ended too; the
 * next request then finds no session and shows the signed-out page.
 */
export async function DELETE(request: NextRequest, context: { params: Promise<{ sid: string }> }) {
  const { sid } = await context.params;
  const session = await currentSession().catch(() => null);
  if (!session) return NextResponse.json({ code: "unauthorized" }, { status: 401 });
  const gone = await endSignIn(session.data.accessToken, sid);
  if (!gone) return NextResponse.json({ code: "sign_in_not_ended" }, { status: 502 });
  return proxyToApi(request, `/me/sign-ins/${encodeURIComponent(sid)}`, { method: "DELETE" });
}
