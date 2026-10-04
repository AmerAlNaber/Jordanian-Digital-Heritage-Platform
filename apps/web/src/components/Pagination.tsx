import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";
import { formatNumber } from "@/lib/format";

export async function Pagination({
  locale,
  page,
  pageSize,
  total,
  query,
}: {
  locale: string;
  page: number;
  pageSize: number;
  total: number;
  query: Record<string, string | undefined>;
}) {
  const t = await getTranslations("catalog");
  const last = Math.max(1, Math.ceil(total / pageSize));
  if (last <= 1) return null;
  const clean = Object.fromEntries(Object.entries(query).filter(([, v]) => v)) as Record<
    string,
    string
  >;
  return (
    <nav
      aria-label={t("results", { count: total })}
      className="font-interface mt-8 flex items-center justify-between text-step-n1"
    >
      {page > 1 ? (
        <Link
          href={{ pathname: "/catalog", query: { ...clean, page: String(page - 1) } }}
          rel="prev"
        >
          {t("previous")}
        </Link>
      ) : (
        <span aria-hidden="true" />
      )}
      <span className="label">
        {formatNumber(page, locale)} / {formatNumber(last, locale)}
      </span>
      {page < last ? (
        <Link
          href={{ pathname: "/catalog", query: { ...clean, page: String(page + 1) } }}
          rel="next"
        >
          {t("next")}
        </Link>
      ) : (
        <span aria-hidden="true" />
      )}
    </nav>
  );
}
