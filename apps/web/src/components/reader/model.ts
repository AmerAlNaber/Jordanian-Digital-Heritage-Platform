// Pure reader logic: which pages are on screen, where they sit, and how matches map onto them.
import type { Region } from "@jdhp/schemas";

import { ReaderError } from "@/lib/reader-client";
import { infoUrl } from "@/lib/tiles";

export type PageInfo = {
  seq: number;
  label: string | null;
  sectionTitle: string | null;
  width: number | null;
  height: number | null;
  inSampleRange: boolean;
};

export type ViewerSource = { seq: number; url: string; x: number; width: number; height: number };
export type Layout = { sources: ViewerSource[]; indices: number[] };
export type OverlayRect = { x: number; y: number; width: number; height: number };
export type EndedReason =
  | "expired"
  | "idle"
  | "revoked"
  | "frozen"
  | "suspended"
  | "device_limit"
  | "grant_required"
  | "unauthorized"
  | "generic";

const ENDED_REASONS = new Set<string>([
  "expired",
  "idle",
  "revoked",
  "frozen",
  "suspended",
  "device_limit",
  "grant_required",
]);

/** Gap between facing pages, in viewport units where one page is one unit wide. */
export const SPREAD_GAP = 0.03;
const DEFAULT_ASPECT = 1.5;

export function clampIndex(index: number, count: number): number {
  if (count <= 0) return 0;
  const whole = Number.isFinite(index) ? Math.trunc(index) : 0;
  return Math.min(Math.max(0, whole), count - 1);
}

/** Pages on screen for an index: alone, or as a spread where the first page stands alone. */
export function spreadFor(index: number, count: number, twoPage: boolean): number[] {
  const current = clampIndex(index, count);
  if (!twoPage || count < 2 || current === 0) return [current];
  const first = current % 2 === 1 ? current : current - 1;
  return first + 1 < count ? [first, first + 1] : [first];
}

/** The index after turning one page (or one spread) forward or back. */
export function step(index: number, count: number, twoPage: boolean, delta: 1 | -1): number {
  const current = spreadFor(index, count, twoPage);
  const last = current[current.length - 1] ?? 0;
  if (delta > 0) return clampIndex(last + 1, count);
  const first = current[0] ?? 0;
  return first === 0 ? 0 : (spreadFor(first - 1, count, twoPage)[0] ?? 0);
}

/** Where each visible page sits. In right-to-left books the lower page number is on the right. */
export function layoutFor(
  work: string,
  pages: PageInfo[],
  index: number,
  twoPage: boolean,
  rtl: boolean,
): Layout {
  const indices = spreadFor(index, pages.length, twoPage);
  const ordered = rtl ? [...indices].reverse() : indices;
  const sources: ViewerSource[] = [];
  let x = 0;
  for (const i of ordered) {
    const page = pages[i];
    if (!page) continue;
    const aspect = page.width && page.height ? page.height / page.width : DEFAULT_ASPECT;
    sources.push({ seq: page.seq, url: infoUrl(work, page.seq), x, width: 1, height: aspect });
    x += 1 + SPREAD_GAP;
  }
  return { sources, indices };
}

/** Matched word boxes in page pixels, placed in viewport units beside the page they belong to. */
export function overlayRects(
  regions: Region[],
  source: ViewerSource,
  pageWidth: number | null,
): OverlayRect[] {
  if (!pageWidth || pageWidth <= 0) return [];
  return regions.map((region) => ({
    x: source.x + region.x / pageWidth,
    y: region.y / pageWidth,
    width: region.w / pageWidth,
    height: region.h / pageWidth,
  }));
}

export function parsePageParam(value: string | string[] | undefined, count: number): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const seq = Number.parseInt(raw ?? "1", 10);
  return clampIndex((Number.isFinite(seq) ? seq : 1) - 1, count);
}

/** Why a session ended, from the API's answer; anything unexpected is "generic". */
export function endedReasonFrom(error: unknown): EndedReason {
  if (error instanceof ReaderError) {
    const reason = error.problem.reason;
    if (reason && ENDED_REASONS.has(reason)) return reason as EndedReason;
    const code = error.problem.code;
    if (code === "device_limit" || code === "grant_required") return code;
    if (error.status === 401 || error.status === 403) return "unauthorized";
  }
  return "generic";
}
