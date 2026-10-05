// Browser-side calls for the reader. Reader endpoints take the grant token as their credential, so
// the heartbeat and closing go straight to the API; anything that acts as the member (opening a
// session, printing, searching with the member's visibility) goes through the backend-for-frontend.
import type { PrintJobOut, PrintLinkOut, ReaderSessionOut, SearchResponse } from "@jdhp/schemas";

import { apiBase } from "./tiles";

export const GRANT_HEADER = "X-Jdhp-Grant";
const DEVICE_KEY = "jdhp_device";

export type Problem = { code?: string; reason?: string; title?: string; quota_remaining?: number };

export class ReaderError extends Error {
  constructor(
    public readonly status: number,
    public readonly problem: Problem,
  ) {
    super(problem.title ?? `request failed with ${status}`);
  }
}

async function call<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}) },
    cache: "no-store",
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new ReaderError(response.status, (body ?? {}) as Problem);
  return body as T;
}

function json(body: unknown, headers: Record<string, string> = {}): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  };
}

/** A stable identifier for this browser, so the device limit means something (ACS-2). */
export function deviceFingerprint(): string {
  let id = "";
  try {
    id = window.localStorage.getItem(DEVICE_KEY) ?? "";
    if (!id) {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
      window.localStorage.setItem(DEVICE_KEY, id);
    }
  } catch {
    id = "no-storage";
  }
  return `${id}:${navigator.platform}:${window.screen.width}x${window.screen.height}`;
}

export function openSession(work: string): Promise<ReaderSessionOut> {
  return call<ReaderSessionOut>(
    "/api/bff/reader/sessions",
    json({ work, device_fingerprint: deviceFingerprint() }),
  );
}

export function heartbeat(
  session: ReaderSessionOut,
  pagesViewed: number[],
  dwellSeconds: number,
): Promise<ReaderSessionOut> {
  return call<ReaderSessionOut>(
    `${apiBase()}/reader/sessions/${session.public_id}/heartbeat`,
    json(
      {
        device_fingerprint: deviceFingerprint(),
        pages_viewed: pagesViewed.slice(0, 100),
        dwell_seconds: Math.min(3600, Math.max(0, Math.round(dwellSeconds))),
      },
      { [GRANT_HEADER]: session.tokens?.grant_token ?? "" },
    ),
  );
}

export function endSession(session: ReaderSessionOut): void {
  void fetch(`${apiBase()}/reader/sessions/${session.public_id}`, {
    method: "DELETE",
    headers: { [GRANT_HEADER]: session.tokens?.grant_token ?? "" },
    keepalive: true,
    credentials: "same-origin",
  }).catch(() => undefined);
}

export function searchInWork(work: string, q: string): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, work, limit: "1", pages_per_work: "10" });
  return call<SearchResponse>(`/api/bff/search?${params.toString()}`, { method: "GET" });
}

export function requestPrint(session: ReaderSessionOut, pages: number[]): Promise<PrintJobOut> {
  return call<PrintJobOut>(
    `/api/bff/reader/sessions/${session.public_id}/print`,
    json({ pages }, { [GRANT_HEADER]: session.tokens?.grant_token ?? "" }),
  );
}

export function printStatus(job: string): Promise<PrintJobOut> {
  return call<PrintJobOut>(`/api/bff/reader/prints/${job}`, { method: "GET" });
}

export function printLink(job: string): Promise<PrintLinkOut> {
  return call<PrintLinkOut>(`/api/bff/reader/prints/${job}/link`, { method: "POST" });
}
