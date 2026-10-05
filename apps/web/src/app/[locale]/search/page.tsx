import type { SearchResponse, TermSummary } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Pagination } from "@/components/Pagination";
import { SearchField } from "@/components/SearchField";
import { type FacetLabels, SearchFacets } from "@/components/search/SearchFacets";
import { SearchResults } from "@/components/search/SearchResults";
import { resolveLocale } from "@/i18n/routing";
import { apiFetch, apiList } from "@/lib/api";
import { apiQuery, parseSearchQuery, toParams } from "@/lib/search-params";

const PAGE_SIZE = 20;
const LABEL_SCHEMES = ["gazetteer_jo", "local_ar", "period_jo", "theme"] as const;

type Params = Promise<{ locale: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const query = parseSearchQuery(await searchParams);
  const t = await getTranslations({ locale, namespace: "search" });
  return {
    title: query.q ? `${query.q} — ${t("title")}` : t("title"),
    robots: { index: false, follow: true },
  };
}

/** Labels for the facet codes, from the controlled vocabularies the works are indexed with. */
async function facetLabels(locale: string): Promise<FacetLabels> {
  const labels: FacetLabels = {};
  const lists = await Promise.all(
    LABEL_SCHEMES.map((scheme) =>
      apiList<TermSummary>(`/vocabulary/${scheme}`, locale, { limit: 100 }).catch(() => null),
    ),
  );
  for (const list of lists) {
    for (const term of list?.items ?? []) {
      labels[term.code] = locale === "ar" ? term.label_ar : (term.label_en ?? term.label_ar);
    }
  }
  return labels;
}

export default async function SearchPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const query = parseSearchQuery(await searchParams);
  const t = await getTranslations("search");
  const [result, labels] = await Promise.all([
    apiFetch<SearchResponse>(`/search?${apiQuery(query, PAGE_SIZE).toString()}`, { locale }),
    facetLabels(locale),
  ]);
  const browsing = !query.q;

  return (
    <div className="pt-12">
      <header className="flex flex-col gap-4">
        <h1 className="text-step-3">{browsing ? t("browseTitle") : t("title")}</h1>
        <SearchField
          locale={locale}
          label={t("query")}
          placeholder=""
          submit={t("submit")}
          defaultValue={query.q}
          compact
        />
        {result.expanded_terms.length > 0 ? (
          <p className="label" dir="auto">
            {t("expanded", { terms: result.expanded_terms.join(" · ") })}
          </p>
        ) : null}
      </header>
      <div className="mt-10 grid gap-10 lg:grid-cols-[14rem_1fr]">
        <SearchFacets locale={locale} query={query} facets={result.facets} labels={labels} />
        <section aria-live="polite">
          <p className="label hairline-bottom pb-3">
            {t("results", { count: result.total_works })}
            {result.total_page_hits > 0
              ? ` · ${t("pageHits", { count: result.total_page_hits })}`
              : ""}
          </p>
          {result.works.length === 0 ? (
            <p className="reading mt-8 text-ink-muted">{t("empty")}</p>
          ) : (
            <SearchResults hits={result.works} locale={locale} query={query.q} />
          )}
          <Pagination
            locale={locale}
            page={query.page}
            pageSize={PAGE_SIZE}
            total={result.total_works}
            query={toParams({ ...query, page: 1 })}
            pathname="/search"
          />
        </section>
      </div>
    </div>
  );
}
