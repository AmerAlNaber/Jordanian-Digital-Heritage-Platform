import type { WorkSummary } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Facets } from "@/components/Facets";
import { Pagination } from "@/components/Pagination";
import { SearchField } from "@/components/SearchField";
import { WorkList } from "@/components/WorkList";
import { apiList } from "@/lib/api";
import { resolveLocale } from "@/i18n/routing";

const ACCESS_CLASSES = ["open", "registered", "paid", "restricted"] as const;
const PAGE_SIZE = 20;

type Search = { q?: string; access_class?: string; page?: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const t = await getTranslations({ locale, namespace: "catalog" });
  return { title: t("title"), alternates: { languages: { ar: "/ar/catalog", en: "/en/catalog" } } };
}

export default async function CatalogPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Search>;
}) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const search = await searchParams;
  const t = await getTranslations("catalog");
  const pageNumber = Math.max(1, Number.parseInt(search.page ?? "1", 10) || 1);
  const accessClass = ACCESS_CLASSES.includes(
    search.access_class as (typeof ACCESS_CLASSES)[number],
  )
    ? search.access_class
    : undefined;
  const result = await apiList<WorkSummary>("/works", locale, {
    q: search.q,
    access_class: accessClass,
    limit: PAGE_SIZE,
    offset: (pageNumber - 1) * PAGE_SIZE,
  });

  return (
    <div className="pt-12">
      <header className="flex flex-col gap-4">
        <h1 className="text-step-3">{t("title")}</h1>
        <SearchField
          locale={locale}
          label={t("query")}
          placeholder=""
          submit={t("query")}
          defaultValue={search.q ?? ""}
          compact
        />
      </header>
      <div className="mt-10 grid gap-10 lg:grid-cols-[14rem_1fr]">
        <Facets locale={locale} classes={ACCESS_CLASSES} selected={accessClass} query={search.q} />
        <section aria-live="polite">
          <p className="label hairline-bottom pb-3">{t("results", { count: result.total })}</p>
          {result.items.length === 0 ? (
            <p className="reading mt-8 text-ink-muted">{t("empty")}</p>
          ) : (
            <WorkList works={result.items} locale={locale} />
          )}
          <Pagination
            locale={locale}
            page={pageNumber}
            pageSize={PAGE_SIZE}
            total={result.total}
            query={{ q: search.q, access_class: accessClass }}
          />
        </section>
      </div>
    </div>
  );
}
