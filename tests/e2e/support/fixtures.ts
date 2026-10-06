import { test as base } from "@playwright/test";

import ar from "../../../apps/web/messages/ar.json" with { type: "json" };
import en from "../../../apps/web/messages/en.json" with { type: "json" };

export type Lang = "ar" | "en";
export type Messages = typeof en;
export type Options = { lang: Lang };

export const messages: Record<Lang, Messages> = { ar: ar as Messages, en };

/** Every test knows which interface language it runs in and has that language's strings. */
export const test = base.extend<Options & { msgs: Messages }>({
  lang: ["ar", { option: true }],
  msgs: async ({ lang }, use) => {
    await use(messages[lang]);
  },
});

export { expect } from "@playwright/test";

export function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}
