import { describe, expect, it, vi } from "vitest";

import { discoverMetadata } from "./oidc";

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
