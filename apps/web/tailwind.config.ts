import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";
import preset from "@jdhp/design-tokens/tailwind";

// Every color, size and radius comes from the token preset; nothing is inherited from Tailwind's
// default palette (SPEC.md: "The tokens must be chosen, not inherited").
const config: Config = {
  presets: [preset],
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  plugins: [typography],
};

export default config;
