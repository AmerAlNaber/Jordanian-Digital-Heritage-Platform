import type { WorkHit } from "@jdhp/schemas";
import { getTranslations } from "next-intl/server";

import { AccessBadge } from "@/components/AccessBadge";
import { Link } from "@/i18n/routing";
import { formatHeritageDate, formatNumber } from "@/lib/format";
import { publiclyViewable, thumbnailUrl } from "@/lib/tiles";

export async function SearchResults({
  hits,
  locale,
  query,
}: {
  hits: WorkHit[];
  locale: string;
  query: string;
}) {
  const t = await getTranslations("search");
  const tc = await getTranslations("catalog");
  return (
    <ol className="flex flex-col">
      {hits.map(({ work, pages, page_hits_total }) => {
        const primary =
          locale === "ar" ? work.title_ar : (work.title_en ?? work.title_translit ?? work.title_ar);
        const secondary = locale === "ar" ? (work.title_en ?? work.title_translit) : work.title_ar;
        return (
          <li key={work.public_id} className="hairline-bottom flex flex-col gap-3 py-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
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
                    tc("pages", { count: work.page_count }),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <AccessBadge accessClass={work.access_class} />
            </div>
            {pages.length > 0 ? (
              <div>
                <p className="label">
                  {t("matchesIn")} · {t("pageHits", { count: page_hits_total })}
                </p>
                <ol className="mt-2 flex flex-wrap gap-3">
                  {pages.map((page) => {
                    const label = page.label ?? formatNumber(page.seq, locale);
                    const showScan =
                      page.scan_visible &&
                      page.thumbnail_available &&
                      publiclyViewable(page.seq, work.sample_page_limit);
                    const body = (
                      <span className="flex flex-col items-center gap-1">
                        <span className="frame flex h-[7.5rem] w-[5.5rem] items-center justify-center overflow-hidden">
                          {showScan ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={thumbnailUrl(work.public_id, page.seq, 120)}
                              alt=""
                              loading="lazy"
                              height={120}
                              className="h-full w-auto object-contain"
                              draggable={false}
                            />
                          ) : (
                            <span className="font-mono text-step-n1 text-ink-muted">{label}</span>
                          )}
                        </span>
                        <span className="label text-step-n2">
                          {t("openPage", { label })}
                          <span className="sr-only">
                            {" · "}
                            {t("regions", { count: page.regions.length })}
                          </span>
                        </span>
                      </span>
                    );
                    return (
                      <li key={page.seq}>
                        {page.scan_visible ? (
                          <Link
                            href={{
                              pathname: `/read/${work.public_id}`,
                              query: { page: String(page.seq), ...(query ? { q: query } : {}) },
                            }}
                            className="no-underline"
                          >
                            {body}
                          </Link>
                        ) : (
                          <span title={t("scanHidden")}>{body}</span>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
