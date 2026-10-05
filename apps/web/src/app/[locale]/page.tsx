import type { WorkSummary } from "@jdhp/schemas";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { SearchField } from "@/components/SearchField";
import { WorkList } from "@/components/WorkList";
import { Link, resolveLocale } from "@/i18n/routing";
import { apiList } from "@/lib/api";
import { formatNumber } from "@/lib/format";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const brand = await getTranslations("brand");
  let recent: WorkSummary[] = [];
  let total = 0;
  try {
    const page = await apiList<WorkSummary>("/works", locale, { limit: 6 });
    recent = page.items;
    total = page.total;
  } catch {
    recent = [];
  }

  return (
    <div className="flex flex-col gap-section-64 pt-section-64">
      <section className="flex flex-col gap-6">
        <p className="label">{brand("tagline")}</p>
        <h1 className="text-step-4">{brand("name")}</h1>
        <p className="reading text-ink-muted">{t("statement")}</p>
        <SearchField
          locale={locale}
          label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          submit={t("search")}
        />
        <p className="label">{t("catalogSize", { count: total })}</p>
      </section>

      <section aria-labelledby="entry-points" className="hairline-top pt-8">
        <h2 id="entry-points" className="text-step-2">
          {t("entryPoints")}
        </h2>
        <ul className="mt-6 grid gap-4 sm:grid-cols-3">
          <li className="frame p-6">
            <Link href="/collections" className="text-step-1 no-underline hover:underline">
              {t("browseCollections")}
            </Link>
          </li>
          <li className="frame p-6">
            <Link href="/subjects/place" className="text-step-1 no-underline hover:underline">
              {t("browsePlaces")}
            </Link>
          </li>
          <li className="frame p-6">
            <Link href="/subjects/period" className="text-step-1 no-underline hover:underline">
              {t("browsePeriods")}
            </Link>
          </li>
        </ul>
      </section>

      {recent.length > 0 ? (
        <section aria-labelledby="recent" className="hairline-top pt-8">
          <h2 id="recent" className="text-step-2">
            {t("recentTitle")}
          </h2>
          <div className="mt-6">
            <WorkList works={recent} locale={locale} />
          </div>
          <p className="label mt-6">{formatNumber(total, locale)}</p>
        </section>
      ) : null}

      <section aria-labelledby="trust" className="hairline-top pt-8">
        <h2 id="trust" className="text-step-2">
          {t("trustTitle")}
        </h2>
        <p className="reading mt-4 text-ink-muted">{t("trustBody")}</p>
      </section>
    </div>
  );
}
