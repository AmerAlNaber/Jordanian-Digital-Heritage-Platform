import { describe, expect, it } from "vitest";

import ar from "../messages/ar.json";
import en from "../messages/en.json";

function keys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object"
      ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe("INT-1: both catalogs are complete at every release", () => {
  it("has the same keys in Arabic and English", () => {
    expect(keys(ar).sort()).toEqual(keys(en).sort());
  });
  it("Arabic plurals carry the categories Arabic needs", () => {
    const plural = keys(ar).filter(
      (k) => k.endsWith("results") || k.endsWith("pages") || k.endsWith("works"),
    );
    for (const key of plural) {
      const value = key
        .split(".")
        .reduce<unknown>((acc, part) => (acc as Record<string, unknown>)[part], ar) as string;
      expect(value, key).toContain("two {");
      expect(value, key).toContain("few {");
      expect(value, key).toContain("many {");
    }
  });
  it("has no empty strings", () => {
    for (const catalog of [ar, en]) {
      for (const key of keys(catalog)) {
        const value = key
          .split(".")
          .reduce<unknown>((acc, part) => (acc as Record<string, unknown>)[part], catalog);
        expect(String(value).trim(), key).not.toBe("");
      }
    }
  });
});
