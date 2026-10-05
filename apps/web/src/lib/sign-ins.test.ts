import type { ReaderSessionSummary } from "@jdhp/schemas";
import { describe, expect, it } from "vitest";

import { currentSid, mergeSignIns } from "./sign-ins";

function reader(id: string, signIn: string | null): ReaderSessionSummary {
  return {
    public_id: id,
    work: "w8abc",
    title_ar: "أخبار",
    title_en: "Chronicle",
    device: "0123abcd",
    sign_in: signIn,
    current_sign_in: false,
    started_at: "2026-10-05T10:00:00Z",
    last_seen_at: "2026-10-05T10:05:00Z",
    idle_expires_at: "2026-10-05T10:35:00Z",
  };
}

function token(payload: object): string {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `eyJhbGciOiJSUzI1NiJ9.${body}.signature`;
}

describe("sign-ins (SEC-5)", () => {
  it("reads the sid claim of the member's own token and nothing else", () => {
    expect(currentSid(token({ sid: "s-1", sub: "u" }))).toBe("s-1");
    expect(currentSid(token({ sub: "u" }))).toBeNull();
    expect(currentSid("not-a-token")).toBeNull();
  });

  it("groups readers under their sign-in, current first, strays last", () => {
    const merged = mergeSignIns(
      [
        { id: "s-phone", browser: "Safari/iOS", started: 1_759_600_000, lastAccess: 1_759_603_600 },
        { id: "s-laptop", browser: "Firefox", current: true },
      ],
      [reader("r1", "s-phone"), reader("r2", "s-laptop"), reader("r3", "s-old")],
      "s-laptop",
    );
    expect(merged.map((s) => s.id)).toEqual(["s-laptop", "s-phone", null]);
    expect(merged[0]?.current).toBe(true);
    expect(merged[1]?.readers.map((r) => r.public_id)).toEqual(["r1"]);
    expect(merged[1]?.startedAt).toBe("2025-10-04T17:46:40.000Z");
    expect(merged[2]?.readers.map((r) => r.public_id)).toEqual(["r3"]);
  });
});
