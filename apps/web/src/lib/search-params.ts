// Search page query handling: facet values are codes from the controlled vocabulary.
export const FACETS = ["subject", "place", "period", "language", "access_class"] as const;
export type FacetParam = (typeof FACETS)[number];

/** The facet aggregation name the API uses for each query parameter. */
export const FACET_AGGREGATION: Record<FacetParam, string> = {
  subject: "subjects",
  place: "places",
  period: "periods",
  language: "language",
  access_class: "access_class",
};

export type SearchQuery = {
  q: string;
  facets: Record<FacetParam, string[]>;
  page: number;
};

type Raw = Record<string, string | string[] | undefined>;

const CODE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

function list(value: string | string[] | undefined): string[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(values.filter((v) => CODE.test(v)))].sort();
}

export function parseSearchQuery(raw: Raw): SearchQuery {
  const q = typeof raw.q === "string" ? raw.q.trim().slice(0, 200) : "";
  const page = Math.max(1, Number.parseInt(String(raw.page ?? "1"), 10) || 1);
  const facets = Object.fromEntries(FACETS.map((f) => [f, list(raw[f])])) as Record<
    FacetParam,
    string[]
  >;
  return { q, facets, page };
}

/** The query string for a link that adds or removes one facet value, back on page one. */
export function toggleFacet(
  query: SearchQuery,
  facet: FacetParam,
  value: string,
): Record<string, string | string[]> {
  const current = query.facets[facet];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  return toParams({ ...query, facets: { ...query.facets, [facet]: next }, page: 1 });
}

export function toParams(query: SearchQuery): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (query.q) params.q = query.q;
  for (const facet of FACETS) {
    if (query.facets[facet].length) params[facet] = query.facets[facet];
  }
  if (query.page > 1) params.page = String(query.page);
  return params;
}

export function hasFilters(query: SearchQuery): boolean {
  return FACETS.some((facet) => query.facets[facet].length > 0);
}

/** The API's query parameters for this search. */
export function apiQuery(query: SearchQuery, pageSize: number): URLSearchParams {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  for (const facet of FACETS) for (const value of query.facets[facet]) params.append(facet, value);
  params.set("limit", String(pageSize));
  params.set("offset", String((query.page - 1) * pageSize));
  params.set("pages_per_work", "5");
  return params;
}
