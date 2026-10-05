import type { CollectionSummary } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Link, resolveLocale } from "@/i18n/routing";
import { apiList } from "@/lib/api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const t = await getTranslations({ locale, namespace: "collections" });
  return {
    title: t("title"),
    alternates: { languages: { ar: "/ar/collections", en: "/en/collections" } },
  };
}

export default async function CollectionsPage({ params }: { params: Promise<{ locale: string }> }) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const t = await getTranslations("collections");
  const result = await apiList<CollectionSummary>("/collections", locale, { limit: 50 });
  return (
    <div className="pt-12">
      <h1 className="text-step-3">{t("title")}</h1>
      {result.items.length === 0 ? (
        <p className="reading mt-8 text-ink-muted">{t("empty")}</p>
      ) : (
        <ul className="mt-8 flex flex-col">
          {result.items.map((c) => (
            <li key={c.public_id} className="hairline-bottom py-6">
              <Link
                href={`/collections/${c.public_id}`}
                className="text-step-2 no-underline hover:underline"
              >
                {locale === "ar" ? c.title_ar : (c.title_en ?? c.title_ar)}
              </Link>
              <p className="label mt-1">{t("works", { count: c.work_count })}</p>
              {(locale === "ar" ? c.description_ar : (c.description_en ?? c.description_ar)) ? (
                <p className="reading mt-2 text-ink-muted">
                  {locale === "ar" ? c.description_ar : (c.description_en ?? c.description_ar)}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
