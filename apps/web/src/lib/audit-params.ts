// Audit viewer query handling (ADM-5): filters are plain identifiers and UTC instants.
export type AuditQuery = {
  actor: string;
  action: string;
  resource_kind: string;
  resource_id: string;
  since: string;
  until: string;
  page: number;
};

export const AUDIT_FILTERS = ["actor", "action", "resource_kind", "resource_id"] as const;
const IDENTIFIER = /^[\w.:@/-]+$/;
const IDENTIFIER_MAX = 128;
const MINUTES = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const SECONDS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/;

type Raw = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  const text = Array.isArray(value) ? value[0] : value;
  return typeof text === "string" ? text.trim() : "";
}

function identifier(value: string | string[] | undefined): string {
  const text = one(value);
  return text.length <= IDENTIFIER_MAX && IDENTIFIER.test(text) ? text : "";
}

/** A `datetime-local` value, read as UTC; anything else is dropped. */
function instant(value: string | string[] | undefined): string {
  const text = one(value);
  const shaped = MINUTES.test(text) || SECONDS.test(text);
  return shaped && !Number.isNaN(Date.parse(`${text}Z`)) ? text : "";
}

/** The instant as the API takes it: seconds and the UTC designator. */
function utc(text: string): string {
  return MINUTES.test(text) ? `${text}:00Z` : `${text}Z`;
}

export function parseAuditQuery(raw: Raw): AuditQuery {
  return {
    actor: identifier(raw.actor),
    action: identifier(raw.action),
    resource_kind: identifier(raw.resource_kind),
    resource_id: identifier(raw.resource_id),
    since: instant(raw.since),
    until: instant(raw.until),
    page: Math.max(1, Number.parseInt(one(raw.page) || "1", 10) || 1),
  };
}

/** The non-empty filters as the API and the page links take them (without the page). */
export function toParams(query: AuditQuery): Record<string, string> {
  const params: Record<string, string> = {};
  for (const key of AUDIT_FILTERS) if (query[key]) params[key] = query[key];
  if (query.since) params.since = utc(query.since);
  if (query.until) params.until = utc(query.until);
  return params;
}

export function apiQuery(query: AuditQuery, pageSize: number): Record<string, string> {
  return {
    ...toParams(query),
    limit: String(pageSize),
    offset: String((query.page - 1) * pageSize),
  };
}

export function exportHref(query: AuditQuery, format: "csv" | "json"): string {
  const params = new URLSearchParams({ ...toParams(query), format });
  return `/api/bff/audit/export?${params.toString()}`;
}
