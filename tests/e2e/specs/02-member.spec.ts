import { expectAccessible } from "../support/axe";
import { expect, test, unique } from "../support/fixtures";
import { subjectOf } from "../support/keycloak";
import { verificationLink, waitForEmail } from "../support/mailpit";
import { latestSmsCode } from "../support/sms";
import { saveMember } from "../support/state";

/**
 * The Phase 1 acceptance path for a member: register in the interface language, verify the
 * email, choose a password, verify a phone, read the seed book and print two pages
 * (ACC-1, RDR-1, RDR-4, SEC-2, SEC-15).
 */
test.describe.serial("a new member", () => {
  const password = `Zaytun-Teen-${unique("e2e")}`;
  let email = "";
  let workPath = "";

  test("registers with email verification and chooses the password afterwards", async ({
    page,
    lang,
    msgs,
  }) => {
    email = `${unique(`member-${lang}`)}@example.test`;
    await page.goto(`/${lang}`);
    await page.getByRole("link", { name: msgs.nav.register }).click();
    // Keycloak's registration form, rendered in the page's language.
    await expect(page.locator("#kc-register-form")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", lang);
    await page.locator("#firstName").fill(lang === "ar" ? "عضو" : "Member");
    await page.locator("#lastName").fill(lang === "ar" ? "تجريبي" : "Test");
    await page.locator("#email").fill(email);
    await expectAccessible(page, `registration (${lang})`);
    await page.locator('input[type="submit"]').click();
    const mail = await waitForEmail(email);
    await page.goto(verificationLink(mail));
    // The password is set after the address is verified (ADR-0009).
    await expect(page.locator("#password-new")).toBeVisible();
    await page.locator("#password-new").fill(password);
    await page.locator("#password-confirm").fill(password);
    await page.locator('input[type="submit"]').click();
    await expect(page).toHaveURL(new RegExp(`/${lang}/account`));
    await expect(page.getByText(msgs.account.signedInAs)).toBeVisible();
    await expect(page.getByText(msgs.account.verifications.email)).toBeVisible();
    saveMember(lang, { email, password, subject: await subjectOf(email) });
  });

  test("verifies a phone number with the code the platform sends", async ({ page, lang, msgs }) => {
    await page.goto(`/${lang}/account`);
    const number = `+96279${String(Math.floor(Math.random() * 1_000_000)).padStart(7, "0")}`;
    await page.getByLabel(msgs.account.phone.numberLabel).fill(number);
    await page.getByRole("button", { name: msgs.account.phone.sendCode }).click();
    await expect(page.getByLabel(msgs.account.phone.codeLabel)).toBeVisible();
    const code = await latestSmsCode();
    await page.getByLabel(msgs.account.phone.codeLabel).fill(code);
    await page.getByRole("button", { name: msgs.account.phone.confirm }).click();
    await expect(page.getByText(msgs.account.verifications.phone)).toBeVisible();
    await expect(page.getByText(/\+962•+\d{2}/)).toBeVisible();
    await expectAccessible(page, `account (${lang})`);
  });

  test("reads the seed book in the secure reader", async ({ page, lang, msgs }) => {
    await page.goto(`/${lang}/search?q=${encodeURIComponent("الكرم")}`);
    await page.getByRole("main").locator('a[href*="/works/"]').first().click();
    await page.getByRole("link", { name: msgs.access.read }).click();
    await expect(page).toHaveURL(new RegExp(`/${lang}/read/`));
    workPath = new URL(page.url()).pathname;
    const tile = page.waitForResponse(
      (r) => r.url().includes("/iiif/3/") && r.status() === 200 && !r.url().endsWith("info.json"),
    );
    await expect(page.locator(".openseadragon-canvas")).toBeVisible({ timeout: 60_000 });
    await tile;
    await page.getByRole("button", { name: msgs.reader.next }).click();
    await expect(page.getByRole("toolbar", { name: msgs.reader.toolbar })).toBeVisible();
    saveMember(lang, { email, password, subject: await subjectOf(email), work: workPath });
  });

  test("prints two pages as a marked low-resolution PDF", async ({ page, lang, msgs }) => {
    await page.goto(workPath);
    await expect(page.locator(".openseadragon-canvas")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: msgs.reader.print }).click();
    await page.getByLabel(msgs.print.range).check();
    await page.getByLabel(msgs.print.from).fill("1");
    await page.getByLabel(msgs.print.to).fill("2");
    await page.getByRole("button", { name: msgs.print.submit }).click();
    await expect(page.getByText(msgs.print.ready)).toBeVisible({ timeout: 120_000 });
    const link = page.getByRole("link", { name: msgs.print.download });
    const href = await link.getAttribute("href");
    expect(href).toBeTruthy();
    const pdf = await page.request.get(href as string);
    expect(pdf.status()).toBe(200);
    const body = await pdf.body();
    expect(body.subarray(0, 5).toString()).toBe("%PDF-");
    expect(body.length).toBeGreaterThan(10_000);
  });
});
