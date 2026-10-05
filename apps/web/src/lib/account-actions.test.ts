import { describe, expect, it } from "vitest";

import { isAccountAction, keycloakAction, loginHref, uiLocale } from "./account-actions";

describe("account actions (ACC-1, ACC-2)", () => {
  it("maps only the allowed actions to Keycloak required actions", () => {
    expect(keycloakAction("totp")).toBe("CONFIGURE_TOTP");
    expect(keycloakAction("passkey")).toBe("webauthn-register-passwordless");
    expect(keycloakAction("password")).toBe("UPDATE_PASSWORD");
    expect(keycloakAction("delete_account")).toBeNull();
    expect(keycloakAction("constructor")).toBeNull();
    expect(keycloakAction(null)).toBeNull();
    expect(isAccountAction("__proto__")).toBe(false);
  });

  it("builds sign-in, registration and action links that return to the page", () => {
    expect(loginHref({ returnTo: "/ar/account" })).toBe("/api/auth/login?return=%2Far%2Faccount");
    expect(loginHref({ returnTo: "/ar", register: true })).toBe(
      "/api/auth/login?return=%2Far&register=1",
    );
    expect(loginHref({ returnTo: "/en/account", action: "passkey" })).toBe(
      "/api/auth/login?return=%2Fen%2Faccount&action=passkey",
    );
    expect(loginHref({ returnTo: "/en/staff", staff: true })).toContain("staff=1");
  });

  it("renders Keycloak in the language of the page the user came from", () => {
    expect(uiLocale("/ar/account")).toBe("ar");
    expect(uiLocale("/en")).toBe("en");
    expect(uiLocale("/en/read/x")).toBe("en");
    expect(uiLocale("/english-not-a-locale")).toBe("ar");
  });
});
