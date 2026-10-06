import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Pagination } from "@/components/Pagination";
import { AuditTable } from "@/components/audit/AuditTable";
import { resolveLocale } from "@/i18n/routing";
import { loginHref } from "@/lib/account-actions";
import { ApiError, apiFetch } from "@/lib/api";
import { apiQuery, exportHref, parseAuditQuery, toParams } from "@/lib/audit-params";
import { currentSession } from "@/lib/session";

import type { Paginated, Schemas } from "@jdhp/schemas";

type AuditEventOut = Schemas["AuditEventOut"];
type ChainVerification = Schemas["ChainVerification"];

const PAGE_SIZE = 50;
const STAFF = new Set(["curator", "reviewer", "rights_officer", "platform_admin"]);
const VIEWERS = new Set(["rights_officer", "platform_admin"]);

type Params = Promise<{ locale: string }>;
type Search = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const t = await getTranslations({ locale, namespace: "audit" });
  return { title: t("title"), robots: { index: false } };
}

/** The audit viewer (ADM-5): search by user, book, action and time; signed exports. */
export default async function AuditPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const t = await getTranslations("audit");
  const session = await currentSession().catch(() => null);
  const roles = session?.data.roles ?? [];
  if (!session || !roles.some((r) => STAFF.has(r))) {
    return (
      <div className="pt-12">
        <h1 className="text-step-3">{t("title")}</h1>
        <p className="reading mt-6 text-ink-muted">{t("staffOnly")}</p>
        <a
          href={loginHref({ returnTo: `/${locale}/staff/audit`, staff: true })}
          className="control control-primary mt-6 inline-flex w-fit"
        >
          {t("staffSignIn")}
        </a>
      </div>
    );
  }
  if (!roles.some((r) => VIEWERS.has(r))) {
    return (
      <div className="pt-12">
        <h1 className="text-step-3">{t("title")}</h1>
        <p className="reading mt-6 text-ink-muted">{t("roleOnly")}</p>
      </div>
    );
  }
  const query = parseAuditQuery(await searchParams);
  let events: Paginated<AuditEventOut> | null = null;
  let chain: ChainVerification | null = null;
  let denied = false;
  try {
    [events, chain] = await Promise.all([
      apiFetch<Paginated<AuditEventOut>>("/audit/events", {
        locale,
        query: apiQuery(query, PAGE_SIZE),
      }),
      apiFetch<ChainVerification>("/audit/verify", { locale }),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) denied = true;
    else throw error;
  }
  const filters = toParams(query);
  return (
    <div className="pt-12">
      <h1 className="text-step-3">{t("title")}</h1>
      <p className="reading mt-3 text-ink-muted">{t("intro")}</p>
      {denied ? <p className="mt-6 text-danger">{t("needMfa")}</p> : null}
      <form method="get" className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(["actor", "action", "resource_kind", "resource_id"] as const).map((name) => (
          <label key={name} className="grid gap-1">
            <span className="label">{t(`filters.${name}`)}</span>
            <input
              name={name}
              defaultValue={query[name]}
              dir="ltr"
              className="control font-mono"
              maxLength={128}
            />
          </label>
        ))}
        <label className="grid gap-1">
          <span className="label">{t("filters.since")}</span>
          <input
            type="datetime-local"
            name="since"
            defaultValue={query.since}
            dir="ltr"
            className="control"
          />
        </label>
        <label className="grid gap-1">
          <span className="label">{t("filters.until")}</span>
          <input
            type="datetime-local"
            name="until"
            defaultValue={query.until}
            dir="ltr"
            className="control"
          />
        </label>
        <div className="flex flex-wrap items-end gap-3 sm:col-span-2 lg:col-span-3">
          <button type="submit" className="control control-primary">
            {t("apply")}
          </button>
          <a href={`/${locale}/staff/audit`} className="control">
            {t("clear")}
          </a>
          <span className="text-step-n1 text-ink-muted">{t("utcNote")}</span>
        </div>
      </form>
      {events ? (
        <>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-step-n1">
            <span>{t("count", { count: events.total })}</span>
            {chain ? (
              <span className={chain.intact ? "label" : "text-danger"}>
                {chain.intact
                  ? t("chainIntact", { count: chain.events_checked })
                  : t("chainBroken", { count: chain.events_checked })}
              </span>
            ) : null}
            <span className="ms-auto flex flex-wrap gap-3">
              <a href={exportHref(query, "csv")} className="control" download>
                {t("exportCsv")}
              </a>
              <a href={exportHref(query, "json")} className="control" download>
                {t("exportJson")}
              </a>
              <a href="/api/bff/audit/export/key" className="control" download>
                {t("exportKey")}
              </a>
            </span>
          </div>
          <p className="mt-2 text-step-n1 text-ink-muted">{t("exportNote")}</p>
          <AuditTable events={events.items} locale={locale} />
          <Pagination
            locale={locale}
            page={query.page}
            pageSize={PAGE_SIZE}
            total={events.total}
            query={filters}
            pathname="/staff/audit"
          />
        </>
      ) : null}
    </div>
  );
}
