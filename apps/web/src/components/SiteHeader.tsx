import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";

import { LocaleSwitcher } from "./LocaleSwitcher";

const STAFF = new Set(["curator", "reviewer", "rights_officer", "platform_admin"]);

export async function SiteHeader({
  locale,
  signedIn,
  roles,
}: {
  locale: string;
  signedIn: boolean;
  roles: string[];
}) {
  const t = await getTranslations("nav");
  const brand = await getTranslations("brand");
  const isStaff = roles.some((r) => STAFF.has(r));
  return (
    <header className="hairline-bottom bg-background">
      <div className="mx-auto flex w-full max-w-[80rem] flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-4 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="font-arabic-display text-step-1 no-underline"
          aria-label={brand("name")}
        >
          {brand("name")}
        </Link>
        <nav
          aria-label={t("menu")}
          className="font-interface flex flex-wrap items-center gap-x-6 gap-y-2 text-step-n1"
        >
          <Link href="/catalog">{t("catalog")}</Link>
          <Link href="/collections">{t("collections")}</Link>
          <Link href="/subjects/place">{t("places")}</Link>
          <Link href="/subjects/period">{t("periods")}</Link>
          <LocaleSwitcher locale={locale} label={t("switchLocale")} />
          {signedIn ? (
            <>
              <Link href="/account">{t("account")}</Link>
              <form action="/api/auth/logout" method="post">
                <button
                  type="submit"
                  className="underline decoration-hairline-strong underline-offset-4 hover:decoration-accent"
                >
                  {t("signOut")}
                </button>
              </form>
            </>
          ) : (
            <a href={`/api/auth/login?return=/${locale}/account`}>{t("signIn")}</a>
          )}
          {isStaff ? (
            <span className="label">{roles.filter((r) => STAFF.has(r)).join(", ")}</span>
          ) : null}
        </nav>
      </div>
    </header>
  );
}
