import type { SearchResponse } from "@jdhp/schemas";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";
import { formatNumber } from "@/lib/format";
import {
  FACET_AGGREGATION,
  FACETS,
  type FacetParam,
  type SearchQuery,
  hasFilters,
  toParams,
  toggleFacet,
} from "@/lib/search-params";

export type FacetLabels = Record<string, string>;

const KNOWN_LANGUAGES = new Set(["ara", "eng", "ota", "fra"]);
const KNOWN_CLASSES = new Set(["open", "registered", "paid", "restricted"]);

export async function SearchFacets({
  locale,
  query,
  facets,
  labels,
}: {
  locale: string;
  query: SearchQuery;
  facets: SearchResponse["facets"];
  labels: FacetLabels;
}) {
  const t = await getTranslations("search");
  const ta = await getTranslations("access");
  const groups = FACETS.map((facet) => ({
    facet,
    buckets: (facets[FACET_AGGREGATION[facet]] ?? []).filter((b) => b.count > 0),
  })).filter((group) => group.buckets.length > 0 || query.facets[group.facet].length > 0);

  function label(facet: FacetParam, value: string): string {
    if (facet === "language")
      return KNOWN_LANGUAGES.has(value) ? t(`languages.${value as "ara"}`) : value;
    if (facet === "access_class") return KNOWN_CLASSES.has(value) ? ta(value as "open") : value;
    return labels[value] ?? value;
  }

  return (
    <aside aria-label={t("filters")} className="font-interface text-step-n1">
      {groups.map(({ facet, buckets }) => (
        <section key={facet} className="mb-6">
          <h2 className="label hairline-bottom pb-2">
            {t(`facets.${FACET_AGGREGATION[facet] as "subjects"}`)}
          </h2>
          <ul className="mt-2 flex flex-col gap-1.5">
            {buckets.map((bucket) => {
              const active = query.facets[facet].includes(bucket.value);
              return (
                <li key={bucket.value} className="flex items-baseline justify-between gap-3">
                  <Link
                    href={{ pathname: "/search", query: toggleFacet(query, facet, bucket.value) }}
                    aria-pressed={active}
                    className={active ? "font-medium" : ""}
                  >
                    {label(facet, bucket.value)}
                  </Link>
                  <span className="label font-mono text-step-n2">
                    {formatNumber(bucket.count, locale)}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {hasFilters(query) ? (
        <p className="mt-2">
          <Link href={{ pathname: "/search", query: toParams({ ...query, facets: emptyFacets(), page: 1 }) }}>
            {t("clear")}
          </Link>
        </p>
      ) : null}
    </aside>
  );
}

function emptyFacets(): Record<FacetParam, string[]> {
  return { subject: [], place: [], period: [], language: [], access_class: [] };
}
