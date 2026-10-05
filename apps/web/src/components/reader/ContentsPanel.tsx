"use client";

import { useTranslations } from "next-intl";

import { formatNumber } from "@/lib/format";

import type { PageInfo } from "./model";

export function ContentsPanel({
  locale,
  pages,
  currentSeqs,
  onSelect,
}: {
  locale: string;
  pages: PageInfo[];
  currentSeqs: number[];
  onSelect: (seq: number) => void;
}) {
  const t = useTranslations("reader");
  const sections = pages.filter((page) => page.sectionTitle);
  const label = (page: PageInfo) => page.label ?? formatNumber(page.seq, locale);
  return (
    <div className="flex flex-col gap-6">
      {sections.length > 0 ? (
        <section aria-labelledby="reader-sections">
          <h2 id="reader-sections" className="label hairline-bottom pb-2">
            {t("sections")}
          </h2>
          <ol className="mt-2 flex flex-col">
            {sections.map((page) => (
              <li key={page.seq}>
                <button
                  type="button"
                  onClick={() => onSelect(page.seq)}
                  aria-current={currentSeqs.includes(page.seq) ? "page" : undefined}
                  className="flex w-full items-baseline justify-between gap-3 py-2 text-start hover:underline"
                >
                  <span className="reading text-step-0">{page.sectionTitle}</span>
                  <span className="label font-mono">{label(page)}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <section aria-labelledby="reader-all-pages">
        <h2 id="reader-all-pages" className="label hairline-bottom pb-2">
          {t("allPages")}
        </h2>
        <ol className="mt-2 grid grid-cols-5 gap-1">
          {pages.map((page) => {
            const current = currentSeqs.includes(page.seq);
            return (
              <li key={page.seq}>
                <button
                  type="button"
                  onClick={() => onSelect(page.seq)}
                  aria-current={current ? "page" : undefined}
                  aria-label={t("page", { label: page.label ?? String(page.seq) })}
                  className={`control min-h-10 w-full px-1 font-mono text-step-n1 ${current ? "control-primary" : ""}`}
                  title={page.inSampleRange ? t("sample") : undefined}
                >
                  {label(page)}
                </button>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
