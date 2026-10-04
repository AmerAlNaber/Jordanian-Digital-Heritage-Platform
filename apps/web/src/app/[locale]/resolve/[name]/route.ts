import type { Resolution } from "@jdhp/schemas";
import { type NextRequest, NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { resolveLocale } from "@/i18n/routing";

/** Persistent identifier resolution (INT-7): /ark:/NAAN/name redirects here, then to the record. */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ locale: string; name: string }> },
) {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  try {
    const resolution = await apiFetch<Resolution>(`/resolve/${encodeURIComponent(name)}`, {
      locale,
    });
    return NextResponse.redirect(
      new URL(
        `/${locale}${resolution.path}`,
        process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:8080",
      ),
      301,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return NextResponse.redirect(
        new URL(
          `/${locale}/not-found`,
          process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:8080",
        ),
        302,
      );
    }
    throw error;
  }
}
