/**
 * Next.js instrumentation hook: runs once when the server process starts. The BFF refuses to
 * serve with incomplete configuration instead of failing on the first sign-in.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { validateEnv } = await import("./lib/env");
    validateEnv();
  }
}
