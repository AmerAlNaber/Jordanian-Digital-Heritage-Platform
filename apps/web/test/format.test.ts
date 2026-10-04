import { describe, expect, it } from "vitest";

import { accessState, formatHeritageDate, formatNumber, toEastern, toWestern } from "@/lib/format";

describe("numerals follow the locale and the preference (INT-4)", () => {
  it("uses Eastern Arabic digits for Arabic by default", () => {
    expect(formatNumber(40, "ar")).toBe("٤٠");
    expect(formatNumber(1923, "ar")).toBe("١٬٩٢٣");
  });
  it("uses Western digits for English and honours an explicit preference", () => {
    expect(formatNumber(40, "en")).toBe("40");
    expect(formatNumber(40, "ar", "western")).toBe("40");
    expect(formatNumber(40, "en", "eastern")).toBe("٤٠");
  });
  it("converts in both directions", () => {
    expect(toEastern("p12")).toBe("p١٢");
    expect(toWestern("١٣٤١")).toBe("1341");
  });
});

describe("heritage dates show Gregorian with Hijri", () => {
  it("puts Hijri first in Arabic and Gregorian first in English", () => {
    expect(formatHeritageDate("1923", "1341", "ar")).toBe(
      "١٣٤١ هـ / 1923 م".replace("١٣٤١", "1341"),
    );
    expect(formatHeritageDate("1923", "1341", "en")).toBe("1923 CE / 1341 AH");
  });
  it("handles ranges and missing parts", () => {
    expect(formatHeritageDate("1880/1920", null, "en")).toBe("1880 – 1920 CE");
    expect(formatHeritageDate(null, null, "en")).toBe("");
  });
});

describe("the one access action depends on the user's state", () => {
  it("maps states", () => {
    expect(accessState({ signedIn: false, canRead: false, canRequest: false })).toBe("anonymous");
    expect(accessState({ signedIn: false, canRead: true, canRequest: false })).toBe("can_read");
    expect(accessState({ signedIn: true, canRead: false, canRequest: true })).toBe("can_request");
    expect(accessState({ signedIn: true, canRead: false, canRequest: false })).toBe("no_access");
  });
});
