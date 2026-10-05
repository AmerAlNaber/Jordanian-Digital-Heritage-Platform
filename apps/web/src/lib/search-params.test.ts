import { describe, expect, it } from "vitest";

import { apiQuery, hasFilters, parseSearchQuery, toParams, toggleFacet } from "./search-params";

describe("search page parameters", () => {
  it("accepts vocabulary codes only and dedupes them", () => {
    const query = parseSearchQuery({
      q: "  الكرم ",
      place: ["wadi-al-karm", "wadi-al-karm", "../x"],
      subject: "agriculture",
      page: "2",
    });
    expect(query.q).toBe("الكرم");
    expect(query.facets.place).toEqual(["wadi-al-karm"]);
    expect(query.facets.subject).toEqual(["agriculture"]);
    expect(query.facets.period).toEqual([]);
    expect(query.page).toBe(2);
    expect(hasFilters(query)).toBe(true);
  });
  it("toggles a facet value and returns to the first page", () => {
    const query = parseSearchQuery({ q: "x", place: "a", page: "3" });
    expect(toggleFacet(query, "place", "b")).toEqual({ q: "x", place: ["a", "b"] });
    expect(toggleFacet(query, "place", "a")).toEqual({ q: "x" });
    expect(toParams(query)).toEqual({ q: "x", place: ["a"], page: "3" });
  });
  it("builds the API query with every facet repeated", () => {
    const query = parseSearchQuery({ q: "x", subject: ["a", "b"], page: "2" });
    const params = apiQuery(query, 20);
    expect(params.getAll("subject")).toEqual(["a", "b"]);
    expect(params.get("offset")).toBe("20");
    expect(params.get("limit")).toBe("20");
    expect(params.get("q")).toBe("x");
    expect(apiQuery(parseSearchQuery({}), 20).has("q")).toBe(false);
  });
});
