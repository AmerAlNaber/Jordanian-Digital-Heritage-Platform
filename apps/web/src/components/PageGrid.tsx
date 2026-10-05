import type { PageSummary } from "@jdhp/schemas";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/routing";
import { formatNumber } from "@/lib/format";
import { publiclyViewable, thumbnailUrl } from "@/lib/tiles";

export function PageGrid({
  pages,
  locale,
  sampleLabel,
  work,
  samplePageLimit,
  canRead,
}: {
  pages: PageSummary[];
  locale: string;
  sampleLabel: string;
  work: string;
  samplePageLimit: number | null;
  canRead: boolean;
}) {
  const t = useTranslations("work");
  return (
    <ol
      className="mt-6 grid grid-cols-4 gap-3 sm:grid-cols-8 lg:grid-cols-10"
      aria-label={t("pagesTitle")}
    >
      {pages.map((page) => {
        const label = page.label ?? formatNumber(page.seq, locale);
        const showScan = page.thumbnail_available && publiclyViewable(page.seq, samplePageLimit);
        const tile = (
          <span className="frame flex aspect-[3/4] flex-col items-center justify-center gap-1 overflow-hidden p-1 text-center">
            {showScan ? (
              // Served by the authorizing gateway with the platform mark; never the original.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={thumbnailUrl(work, page.seq, 240)}
                alt=""
                loading="lazy"
                width={
                  page.width_px
                    ? Math.round((page.width_px * 240) / (page.height_px ?? 1))
                    : undefined
                }
                height={240}
                className="h-full w-full object-contain"
                draggable={false}
              />
            ) : (
              <span className="font-mono text-step-n2 text-ink-muted">{label}</span>
            )}
          </span>
        );
        return (
          <li key={page.seq} className="flex flex-col items-center gap-1">
            {canRead ? (
              <Link
                href={{ pathname: `/read/${work}`, query: { page: String(page.seq) } }}
                aria-label={t("pageLabel", { label: page.label ?? String(page.seq) })}
                className="block w-full no-underline"
              >
                {tile}
              </Link>
            ) : (
              <span
                aria-label={t("pageLabel", { label: page.label ?? String(page.seq) })}
                className="block w-full"
              >
                {tile}
              </span>
            )}
            <span className="label text-step-n2">
              {label}
              {page.in_sample_range ? (
                <span className="text-label-human"> · {sampleLabel}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
