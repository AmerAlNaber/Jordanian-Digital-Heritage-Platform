import { expectAccessible } from "../support/axe";
import { expect, test, unique } from "../support/fixtures";
import { createStaffUser } from "../support/keycloak";
import { loadMember } from "../support/state";
import { totp } from "../support/totp";

/**
 * A rights officer signs in with a password and, on the first sign-in, enrols a one-time code
 * (SEC-3), then finds every action of the member in the audit viewer and takes a signed export
 * (ADM-5, SEC-25).
 */
test.describe.serial("a rights officer", () => {
  test("must enrol a one-time code and then reads the member's trail in the audit log", async ({
    page,
    lang,
    msgs,
  }) => {
    const member = loadMember(lang);
    const email = `${unique(`officer-${lang}`)}@example.test`;
    const password = `Officer-${unique("pw")}`;
    await createStaffUser(email, password, "rights_officer");

    await page.goto(`/${lang}/staff/audit`);
    await page.getByRole("link", { name: msgs.audit.staffSignIn }).click();
    await page.locator("#username").fill(email);
    await page.locator("#kc-login").click();
    await page.locator("#password").fill(password);
    await page.locator("#kc-login").click();
    // No code enrolled yet: Keycloak demands one before anything else (SEC-3).
    await expect(page.locator("#kc-totp-settings-form")).toBeVisible();
    await page.locator("#mode-manual").click();
    const secret = (await page.locator("#kc-totp-secret-key").textContent()) ?? "";
    expect(secret.replace(/\s/g, "").length).toBeGreaterThan(10);
    await page.locator("#totp").fill(totp(secret));
    const label = page.locator("#userLabel");
    if (await label.count()) await label.fill("e2e authenticator");
    await page.locator('input[type="submit"]').click();

    await expect(page).toHaveURL(new RegExp(`/${lang}/staff/audit`));
    await expect(page.getByRole("heading", { level: 1, name: msgs.audit.title })).toBeVisible();
    await expect(page.getByText(msgs.audit.chainIntact.split("{")[0] ?? "")).toBeVisible();

    await page.getByLabel(msgs.audit.filters.actor).fill(member.subject ?? "");
    await page.getByRole("button", { name: msgs.audit.apply }).click();
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    for (const action of ["reader.session_open", "print.request", "account.phone_verified"]) {
      await expect(table.getByText(action, { exact: true }).first()).toBeVisible();
    }
    await expectAccessible(page, `audit viewer (${lang})`);

    const csvHref = await page
      .getByRole("link", { name: msgs.audit.exportCsv })
      .getAttribute("href");
    expect(csvHref).toBeTruthy();
    const csv = await page.request.get(csvHref as string);
    expect(csv.status()).toBe(200);
    expect(csv.headers()["x-jdhp-signature"]).toMatch(/^ed25519=/);
    expect(csv.headers()["digest"]).toMatch(/^sha-256=/);
    const text = (await csv.body()).toString("utf8").replace(/^﻿/, "");
    expect(text.split("\n")[0]).toContain("seq,occurred_at,actor_id");
    expect(text).toContain("print.request");
  });
});
