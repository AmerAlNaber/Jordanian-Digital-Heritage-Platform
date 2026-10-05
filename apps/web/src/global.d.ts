import type messages from "../messages/en.json";

declare global {
  // next-intl: typed message keys from the English catalog; the Arabic catalog has the same keys (tested).
  type IntlMessages = typeof messages;
}

declare module "next-intl" {
  interface AppConfig {
    Messages: IntlMessages;
    Locale: "ar" | "en";
  }
}
