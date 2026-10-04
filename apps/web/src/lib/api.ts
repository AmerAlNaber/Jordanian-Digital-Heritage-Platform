// Server-side API client. Every call carries the interface language and, when signed in, the
// access token. Responses are typed from the OpenAPI document (packages/schemas).
import type { Paginated, Problem } from "@jdhp/schemas";

import { env } from "./env";
import { currentSession } from "./session";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly problem: Problem | null,
  ) {
    super(problem?.title ?? `API error ${status}`);
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, query?: Query): string {
  const url = new URL(path, env("API_INTERNAL_URL").replace(/\/?$/, "/"));
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "")
      url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export async function apiFetch<T>(
  path: string,
  { locale, query, init }: { locale: string; query?: Query; init?: RequestInit },
): Promise<T> {
  const session = await currentSession();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  headers.set("Accept-Language", locale);
  if (session) headers.set("Authorization", `Bearer ${session.data.accessToken}`);
  const response = await fetch(buildUrl(path.replace(/^\//, ""), query), {
    ...init,
    headers,
    cache: session ? "no-store" : (init?.cache ?? "no-store"),
    next: session ? undefined : { revalidate: 60 },
  });
  if (!response.ok) {
    let problem: Problem | null = null;
    try {
      problem = (await response.json()) as Problem;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}

export async function apiList<T>(
  path: string,
  locale: string,
  query?: Query,
): Promise<Paginated<T>> {
  return apiFetch<Paginated<T>>(path, { locale, query });
}
