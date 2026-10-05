import type { CollectionDetail } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { WorkList } from "@/components/WorkList";
import { ApiError, apiFetch } from "@/lib/api";
import { resolveLocale } from "@/i18n/routing";

type Params = Promise<{ locale: string; name: string }>;

async function load(name: string, locale: string): Promise<CollectionDetail | null> {
  try {
    return await apiFetch<CollectionDetail>(`/collections/${encodeURIComponent(name)}`, { locale });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  const collection = await load(name, locale);
  if (!collection) return {};
  return {
    title: locale === "ar" ? collection.title_ar : (collection.title_en ?? collection.title_ar),
  };
}

export default async function CollectionPage({ params }: { params: Params }) {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  setRequestLocale(locale);
  const collection = await load(name, locale);
  if (!collection) notFound();
  const t = await getTranslations("collections");
  const description =
    locale === "ar"
      ? collection.description_ar
      : (collection.description_en ?? collection.description_ar);
  return (
    <div className="pt-12">
      <p className="label font-mono">{collection.ark}</p>
      <h1 className="mt-2 text-step-3">
        {locale === "ar" ? collection.title_ar : (collection.title_en ?? collection.title_ar)}
      </h1>
      {description ? <p className="reading mt-4 text-ink-muted">{description}</p> : null}
      <p className="label hairline-bottom mt-8 pb-3">
        {t("works", { count: collection.work_count })}
      </p>
      <WorkList works={collection.works} locale={locale} />
    </div>
  );
}
