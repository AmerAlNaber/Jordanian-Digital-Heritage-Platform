import { expectAccessible } from "../support/axe";
import { expect, test } from "../support/fixtures";

/** Public discovery: home, search by a word from inside the book, the record (CAT-4, ACX-1, INT-1). */
test.describe("public catalog", () => {
  test("the home page is in the interface language and accessible", async ({
    page,
    lang,
    msgs,
  }) => {
    await page.goto(`/${lang}`);
    await expect(page.locator("html")).toHaveAttribute("lang", lang);
    await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("link", { name: msgs.nav.register })).toBeVisible();
    await expectAccessible(page, `home (${lang})`);
  });

  test("a word from the scanned text finds the seed book and opens its record", async ({
    page,
    lang,
    msgs,
  }) => {
    await page.goto(`/${lang}/search?q=${encodeURIComponent("الكرم")}`);
    const results = page.getByRole("main");
    const record = results.locator('a[href*="/works/"]').first();
    await expect(record).toBeVisible();
    await expectAccessible(page, `search (${lang})`);
    await record.click();
    await expect(page).toHaveURL(new RegExp(`/${lang}/works/`));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: msgs.work.pagesTitle })).toBeVisible();
    await expectAccessible(page, `record (${lang})`);
  });
});
