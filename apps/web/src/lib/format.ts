// Numerals follow the locale and the user's preference (INT-4); dates show Gregorian with Hijri on
// heritage dates. Pure functions so they can be tested without a browser.
export type Numerals = "eastern" | "western";

const EASTERN = "٠١٢٣٤٥٦٧٨٩";

export function formatNumber(value: number, locale: string, numerals?: Numerals): string {
  const system = numerals ?? (locale === "ar" ? "eastern" : "western");
  const base = new Intl.NumberFormat(locale === "ar" ? "ar-JO" : "en-GB", {
    useGrouping: true,
  }).format(value);
  return system === "eastern" ? toEastern(base) : toWestern(base);
}

export function toEastern(text: string): string {
  return text.replace(/[0-9]/g, (d) => EASTERN[Number(d)] ?? d);
}

export function toWestern(text: string): string {
  return text.replace(/[٠-٩]/g, (d) => String(EASTERN.indexOf(d)));
}

/** EDTF year or range to a display string; Hijri is appended when the record carries it. */
export function formatHeritageDate(
  edtf: string | null | undefined,
  hijri: string | null | undefined,
  locale: string,
): string {
  if (!edtf && !hijri) return "";
  const gregorian = edtf
    ? edtf.replace("/", " – ").replace(/~|\?/g, locale === "ar" ? " تقريبًا" : " approx.")
    : "";
  const h = hijri ? (locale === "ar" ? `${hijri} هـ` : `${hijri} AH`) : "";
  const g = gregorian ? (locale === "ar" ? `${gregorian} م` : `${gregorian} CE`) : "";
  const parts = locale === "ar" ? [h, g] : [g, h];
  return parts.filter(Boolean).join(locale === "ar" ? " / " : " / ");
}

export type AccessState = "anonymous" | "can_read" | "can_request" | "no_access";

export function accessState(opts: {
  signedIn: boolean;
  canRead: boolean;
  canRequest: boolean;
}): AccessState {
  if (opts.canRead) return "can_read";
  if (!opts.signedIn) return "anonymous";
  if (opts.canRequest) return "can_request";
  return "no_access";
}
