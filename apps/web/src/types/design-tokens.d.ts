declare module "@jdhp/design-tokens/tailwind" {
  import type { Config } from "tailwindcss";

  /** Tailwind preset built from packages/design-tokens/tokens.json (pnpm --filter @jdhp/design-tokens build). */
  const preset: Partial<Config>;
  export default preset;
}
