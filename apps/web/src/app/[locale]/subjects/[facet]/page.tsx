import type { TermSummary } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { apiList } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { resolveLocale } from "@/i18n/routing";

const SCHEMES: Record<string, string> = {
  place: "gazetteer_jo",
  period: "period_jo",
  subject: "local_ar",
  material: "material",
  theme: "theme",
};

type Params = Promise<{ locale: string; facet: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale: requestedLocale, facet } = await params;
  const locale = resolveLocale(requestedLocale);
  if (!(facet in SCHEMES)) return {};
  const t = await getTranslations({ locale, namespace: "subjects" });
  return { title: t(facet as "place" | "period" | "subject" | "material" | "theme") };
}

export default async function SubjectsPage({ params }: { params: Params }) {
  const { locale: requestedLocale, facet } = await params;
  const locale = resolveLocale(requestedLocale);
  setRequestLocale(locale);
  const scheme = SCHEMES[facet];
  if (!scheme) notFound();
  const t = await getTranslations("subjects");
  const result = await apiList<TermSummary>(`/vocabulary/${scheme}`, locale, { limit: 100 });
  const terms = result.items.filter((term) => term.facet === facet);
  return (
    <div className="pt-12">
      <h1 className="text-step-3">
        {t(facet as "place" | "period" | "subject" | "material" | "theme")}
      </h1>
      {terms.length === 0 ? (
        <p className="reading mt-8 text-ink-muted">{t("empty")}</p>
      ) : (
        <ul className="mt-8 grid gap-x-8 sm:grid-cols-2">
          {terms.map((term) => (
            <li
              key={`${term.scheme}:${term.code}`}
              className="hairline-bottom flex items-baseline justify-between gap-4 py-4"
            >
              <span className="text-step-1">
                {locale === "ar" ? term.label_ar : (term.label_en ?? term.label_ar)}
              </span>
              <span className="label font-mono" aria-label={t("works", { count: term.work_count })}>
                {formatNumber(term.work_count, locale)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
