import { describe, expect, it } from "vitest";

import { ReaderError } from "@/lib/reader-client";

import {
  clampIndex,
  endedReasonFrom,
  layoutFor,
  overlayRects,
  parsePageParam,
  spreadFor,
  step,
} from "./model";

const pages = Array.from({ length: 7 }, (_, i) => ({
  seq: i + 1,
  label: String(i + 1),
  sectionTitle: null,
  width: 1000,
  height: 1500,
  inSampleRange: i < 3,
}));

describe("RDR-3: page navigation", () => {
  it("clamps indices into the book", () => {
    expect(clampIndex(-3, 7)).toBe(0);
    expect(clampIndex(99, 7)).toBe(6);
    expect(clampIndex(Number.NaN, 7)).toBe(0);
    expect(clampIndex(2, 0)).toBe(0);
  });
  it("shows the first page alone and then facing pairs in two-page view", () => {
    expect(spreadFor(0, 7, true)).toEqual([0]);
    expect(spreadFor(1, 7, true)).toEqual([1, 2]);
    expect(spreadFor(2, 7, true)).toEqual([1, 2]);
    expect(spreadFor(5, 7, true)).toEqual([5, 6]);
    expect(spreadFor(6, 6, true)).toEqual([5]);
    expect(spreadFor(4, 7, false)).toEqual([4]);
  });
  it("turns one page or one spread at a time and stops at the covers", () => {
    expect(step(0, 7, false, 1)).toBe(1);
    expect(step(6, 7, false, 1)).toBe(6);
    expect(step(0, 7, false, -1)).toBe(0);
    expect(step(0, 7, true, 1)).toBe(1);
    expect(step(1, 7, true, 1)).toBe(3);
    expect(step(3, 7, true, -1)).toBe(1);
    expect(step(1, 7, true, -1)).toBe(0);
  });
  it("reads page query parameters as one-based numbers", () => {
    expect(parsePageParam("3", 7)).toBe(2);
    expect(parsePageParam(["5", "9"], 7)).toBe(4);
    expect(parsePageParam("nope", 7)).toBe(0);
    expect(parsePageParam("40", 7)).toBe(6);
    expect(parsePageParam(undefined, 7)).toBe(0);
  });
});

describe("INT-2: right-to-left books put the lower page number on the right", () => {
  it("lays facing pages out by reading direction", () => {
    const rtl = layoutFor("w8abc", pages, 1, true, true);
    expect(rtl.indices).toEqual([1, 2]);
    expect(rtl.sources.map((s) => s.seq)).toEqual([3, 2]);
    expect(rtl.sources[0]?.x).toBe(0);
    expect(rtl.sources[1]?.x ?? 0).toBeGreaterThan(1);
    const ltr = layoutFor("w8abc", pages, 1, true, false);
    expect(ltr.sources.map((s) => s.seq)).toEqual([2, 3]);
    expect(ltr.sources[0]?.url).toBe("/iiif/3/w8abc-p0002/info.json");
    expect(ltr.sources[0]?.height).toBe(1.5);
  });
});

describe("SRCH-4: highlights are boxes on the scan", () => {
  it("maps page pixels to viewport units beside the page", () => {
    const source = { seq: 1, url: "/iiif/3/w8abc-p0001/info.json", x: 0, width: 1, height: 1.5 };
    expect(layoutFor("w8abc", pages, 0, false, true).sources).toEqual([source]);
    const rects = overlayRects([{ x: 100, y: 250, w: 200, h: 50 }], source, 1000);
    expect(rects).toEqual([{ x: 0.1, y: 0.25, width: 0.2, height: 0.05 }]);
    const shifted = overlayRects([{ x: 0, y: 0, w: 10, h: 10 }], { ...source, x: 1.03 }, 1000);
    expect(shifted[0]?.x).toBeCloseTo(1.03);
    expect(overlayRects([{ x: 0, y: 0, w: 10, h: 10 }], source, null)).toEqual([]);
  });
});

describe("RDR-5: the reason a session ended", () => {
  it("uses the API's reason, then its code, then the status", () => {
    expect(endedReasonFrom(new ReaderError(401, { code: "reader_session_ended", reason: "idle" }))).toBe("idle");
    expect(endedReasonFrom(new ReaderError(403, { code: "device_limit" }))).toBe("device_limit");
    expect(endedReasonFrom(new ReaderError(403, { code: "grant_required" }))).toBe("grant_required");
    expect(endedReasonFrom(new ReaderError(401, { code: "unauthorized" }))).toBe("unauthorized");
    expect(endedReasonFrom(new ReaderError(500, {}))).toBe("generic");
    expect(endedReasonFrom(new Error("network"))).toBe("generic");
  });
});
