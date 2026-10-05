import type { PageSummary } from "@jdhp/schemas";
import { useTranslations } from "next-intl";

import { formatNumber } from "@/lib/format";

export function PageGrid({
  pages,
  locale,
  sampleLabel,
}: {
  pages: PageSummary[];
  locale: string;
  sampleLabel: string;
}) {
  const t = useTranslations("work");
  return (
    <ol
      className="mt-6 grid grid-cols-4 gap-3 sm:grid-cols-8 lg:grid-cols-10"
      aria-label={t("pagesTitle")}
    >
      {pages.map((page) => (
        <li
          key={page.seq}
          className="frame flex aspect-[3/4] flex-col items-center justify-center gap-1 p-2 text-center"
        >
          <span
            className="font-mono text-step-n2 text-ink-muted"
            aria-label={t("pageLabel", { label: page.label ?? String(page.seq) })}
          >
            {page.label ?? formatNumber(page.seq, locale)}
          </span>
          {page.in_sample_range ? (
            <span className="label text-step-n2 text-label-human">{sampleLabel}</span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
