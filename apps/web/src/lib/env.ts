// Server-only configuration. validateEnv() runs from instrumentation.ts when the Node.js server
// starts, so a missing value stops the process before it serves a request.
const required = [
  "API_INTERNAL_URL",
  "OIDC_ISSUER",
  "OIDC_WEB_CLIENT_ID",
  "OIDC_WEB_CLIENT_SECRET",
  "OIDC_STAFF_CLIENT_ID",
  "OIDC_STAFF_CLIENT_SECRET",
  "SESSION_SECRET",
  "REDIS_URL",
] as const;

type Key = (typeof required)[number];

/** Read every required variable once at startup; throws on the first missing or invalid one. */
export function validateEnv(): void {
  for (const key of required) env(key);
}

export function env(key: Key | "OIDC_INTERNAL_ISSUER" | "NEXT_PUBLIC_BASE_URL"): string {
  const value = process.env[key];
  if (!value) {
    if (key === "OIDC_INTERNAL_ISSUER") return env("OIDC_ISSUER");
    if (key === "NEXT_PUBLIC_BASE_URL") return "http://localhost:8080";
    throw new Error(`missing environment variable ${key}`);
  }
  if (key === "SESSION_SECRET" && value.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 characters");
  }
  return value;
}

export const isProduction = process.env.NODE_ENV === "production";
