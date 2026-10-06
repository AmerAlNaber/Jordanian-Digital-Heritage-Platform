import { describe, expect, it } from "vitest";

import { apiQuery, exportHref, parseAuditQuery, toParams } from "./audit-params";

describe("audit viewer query (ADM-5)", () => {
  it("keeps identifiers and UTC instants, drops anything else", () => {
    const query = parseAuditQuery({
      actor: " omar ",
      action: "reader.session_open",
      resource_kind: "work",
      resource_id: "w8abc/def",
      since: "2026-10-05T10:00",
      until: "not a time",
      page: "3",
    });
    expect(query).toEqual({
      actor: "omar",
      action: "reader.session_open",
      resource_kind: "work",
      resource_id: "w8abc/def",
      since: "2026-10-05T10:00",
      until: "",
      page: 3,
    });
    expect(parseAuditQuery({ actor: "<script>", page: "-1" })).toMatchObject({
      actor: "",
      page: 1,
    });
  });

  it("sends only the filters that are set, as UTC instants, with paging", () => {
    const query = parseAuditQuery({ actor: "omar", since: "2026-10-05T10:00", page: "2" });
    expect(toParams(query)).toEqual({ actor: "omar", since: "2026-10-05T10:00:00Z" });
    expect(apiQuery(query, 50)).toEqual({
      actor: "omar",
      since: "2026-10-05T10:00:00Z",
      limit: "50",
      offset: "50",
    });
    expect(exportHref(query, "csv")).toBe(
      "/api/bff/audit/export?actor=omar&since=2026-10-05T10%3A00%3A00Z&format=csv",
    );
  });
});
