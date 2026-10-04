import { getTranslations } from "next-intl/server";

export async function SiteFooter({ locale }: { locale: string }) {
  const t = await getTranslations("footer");
  const nav = await getTranslations("nav");
  return (
    <footer className="hairline-top mt-section-64">
      <div className="mx-auto flex w-full max-w-[80rem] flex-col gap-4 px-4 py-8 sm:px-6 lg:px-8">
        <p className="label max-w-measure">{t("notice")}</p>
        <nav aria-label={t("about")} className="label flex flex-wrap gap-x-6 gap-y-2">
          <a href="/llms.txt">{t("openData")}</a>
          <a href={`/api/auth/login?staff=1&return=/${locale}/account`}>{nav("staffSignIn")}</a>
        </nav>
      </div>
    </footer>
  );
}
