import { defineConfig, devices } from "@playwright/test";

import type { Options } from "./support/fixtures";

/**
 * The suite runs against a full stack (Compose in CI): one worker, files in order, because the
 * member and staff flows build on each other. Two projects cover both interface languages and
 * both colour schemes (SPEC: tests/e2e, both languages, both themes).
 */
export default defineConfig<Options>({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    ignoreHTTPSErrors: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    {
      name: "ar",
      use: { ...devices["Desktop Chrome"], locale: "ar-JO", colorScheme: "light", lang: "ar" },
    },
    {
      name: "en",
      use: { ...devices["Desktop Chrome"], locale: "en-GB", colorScheme: "dark", lang: "en" },
    },
  ],
});
