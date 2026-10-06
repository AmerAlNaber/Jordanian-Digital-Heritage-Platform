import { describe, expect, it, vi } from "vitest";

import { discoverMetadata, sessionRoles, tokenPayload } from "./oidc";

const PUBLIC = "http://localhost:8080/auth/realms/jdhp";
const INTERNAL = "http://keycloak:8080/auth/realms/jdhp";

function fetchReturning(body: unknown, status = 200): typeof fetch {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as typeof fetch;
}

describe("OIDC discovery behind the edge (SEC-1, ADR-0002)", () => {
  it("asks the internal address and accepts a document that names the public issuer", async () => {
    const fetchMock = fetchReturning({
      issuer: PUBLIC,
      authorization_endpoint: `${PUBLIC}/protocol/openid-connect/auth`,
      token_endpoint: `${INTERNAL}/protocol/openid-connect/token`,
    });
    const metadata = await discoverMetadata(INTERNAL, PUBLIC, fetchMock);
    expect(metadata.issuer).toBe(PUBLIC);
    expect(metadata.token_endpoint).toContain("keycloak:8080");
    expect(fetchMock).toHaveBeenCalledWith(
      `${INTERNAL}/.well-known/openid-configuration`,
      expect.anything(),
    );
  });

  it("refuses a document for another issuer", async () => {
    const fetchMock = fetchReturning({ issuer: "http://evil.test/auth/realms/jdhp" });
    await expect(discoverMetadata(INTERNAL, PUBLIC, fetchMock)).rejects.toThrow(/issuer mismatch/);
  });

  it("refuses a failed discovery response", async () => {
    await expect(discoverMetadata(INTERNAL, PUBLIC, fetchReturning({}, 503))).rejects.toThrow(
      /503/,
    );
  });
});

function jwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "RS256" })}.${b64(payload)}.signature`;
}

describe("tokenPayload", () => {
  it("reads the payload of a compact JWT", () => {
    expect(tokenPayload(jwt({ sub: "u1", realm_access: { roles: ["staff"] } }))).toEqual({
      sub: "u1",
      realm_access: { roles: ["staff"] },
    });
  });

  it("answers undefined for nothing, a malformed token or a non-object payload", () => {
    expect(tokenPayload(undefined)).toBeUndefined();
    expect(tokenPayload("not-a-token")).toBeUndefined();
    expect(tokenPayload("a.%%%.c")).toBeUndefined();
    expect(tokenPayload(`a.${Buffer.from("42").toString("base64url")}.c`)).toBeUndefined();
  });
});

describe("sessionRoles", () => {
  it("takes realm roles from the access token when the ID token carries none (SEC-3)", () => {
    const access = jwt({ realm_access: { roles: ["rights_officer", "staff", "member"] } });
    expect(sessionRoles({ sub: "u1" }, access)).toEqual(["rights_officer", "staff", "member"]);
  });

  it("merges both tokens without repeating a role", () => {
    const access = jwt({ realm_access: { roles: ["member", "staff"] } });
    expect(sessionRoles({ realm_access: { roles: ["member"] } }, access)).toEqual([
      "member",
      "staff",
    ]);
  });
});
