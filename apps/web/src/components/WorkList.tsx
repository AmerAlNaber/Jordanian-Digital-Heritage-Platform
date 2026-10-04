import type { WorkSummary } from "@jdhp/schemas";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";
import { formatHeritageDate, formatNumber } from "@/lib/format";

import { AccessBadge } from "./AccessBadge";

export async function WorkList({ works, locale }: { works: WorkSummary[]; locale: string }) {
  const t = await getTranslations("catalog");
  return (
    <ol className="flex flex-col">
      {works.map((work) => {
        const primary =
          locale === "ar" ? work.title_ar : (work.title_en ?? work.title_translit ?? work.title_ar);
        const secondary = locale === "ar" ? (work.title_en ?? work.title_translit) : work.title_ar;
        return (
          <li
            key={work.public_id}
            className="hairline-bottom grid gap-4 py-6 sm:grid-cols-[5rem_1fr_auto]"
          >
            <div className="frame hidden aspect-[3/4] sm:block" aria-hidden="true" />
            <div className="flex flex-col gap-1">
              <Link
                href={`/works/${work.public_id}`}
                className="text-step-2 no-underline hover:underline"
                lang={locale === "ar" || !work.title_en ? "ar" : "en"}
              >
                {primary}
              </Link>
              {secondary ? (
                <p
                  className="text-ink-muted"
                  lang={locale === "ar" ? "en" : "ar"}
                  dir={locale === "ar" ? "ltr" : "rtl"}
                >
                  {secondary}
                </p>
              ) : null}
              <p className="label">
                {[
                  formatHeritageDate(work.date_edtf, work.date_hijri, locale),
                  t("pages", { count: work.page_count }),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            <div className="flex items-start gap-3 sm:flex-col sm:items-end">
              <AccessBadge accessClass={work.access_class} />
              <span className="label font-mono" aria-hidden="true">
                {formatNumber(work.page_count, locale)}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
