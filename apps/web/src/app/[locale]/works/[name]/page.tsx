import type { ContentObjectOut, PageSummary, WorkDetail } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { AccessAction } from "@/components/AccessAction";
import { AccessBadge } from "@/components/AccessBadge";
import { CitationBlock } from "@/components/CitationBlock";
import { PageGrid } from "@/components/PageGrid";
import { ProvenanceLabel } from "@/components/ProvenanceLabel";
import { RecordField } from "@/components/RecordField";
import { Link, resolveLocale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api";
import { formatHeritageDate } from "@/lib/format";
import { currentSession } from "@/lib/session";

type Params = Promise<{ locale: string; name: string }>;

async function loadWork(name: string, locale: string): Promise<WorkDetail | null> {
  try {
    return await apiFetch<WorkDetail>(`/works/${encodeURIComponent(name)}`, { locale });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  const work = await loadWork(name, locale);
  if (!work) return {};
  const title =
    locale === "ar" ? work.title_ar : (work.title_en ?? work.title_translit ?? work.title_ar);
  const description =
    locale === "ar" ? work.description_ar : (work.description_en ?? work.description_ar);
  return {
    title,
    description: description ?? undefined,
    alternates: { languages: { ar: `/ar/works/${name}`, en: `/en/works/${name}` } },
    openGraph: { title, description: description ?? undefined, type: "book" },
  };
}

export default async function WorkPage({ params }: { params: Params }) {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  setRequestLocale(locale);
  const work = await loadWork(name, locale);
  if (!work) notFound();
  const t = await getTranslations("work");
  const ta = await getTranslations("access");
  const session = await currentSession().catch(() => null);
  const [pages, content] = await Promise.all([
    apiFetch<PageSummary[]>(`/works/${encodeURIComponent(name)}/pages`, { locale }).catch(
      () => [] as PageSummary[],
    ),
    apiFetch<ContentObjectOut[]>(`/works/${encodeURIComponent(name)}/content`, { locale }).catch(
      () => [] as ContentObjectOut[],
    ),
  ]);

  const title =
    locale === "ar" ? work.title_ar : (work.title_en ?? work.title_translit ?? work.title_ar);
  const otherTitle = locale === "ar" ? (work.title_en ?? work.title_translit) : work.title_ar;
  const description =
    locale === "ar" ? work.description_ar : (work.description_en ?? work.description_ar);
  const byFacet = (facet: string) => work.terms.filter((term) => term.facet === facet);
  const label = (term: { label_ar: string; label_en: string | null }) =>
    locale === "ar" ? term.label_ar : (term.label_en ?? term.label_ar);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Book",
    name: work.title_ar,
    alternateName: [work.title_en, work.title_translit].filter(Boolean),
    author: work.agents
      .filter((a) => a.role === "author")
      .map((a) => ({
        "@type": "Person",
        name: a.name_ar,
        alternateName: a.name_latin ?? undefined,
      })),
    inLanguage: work.language,
    datePublished: work.date_edtf ?? undefined,
    numberOfPages: work.page_count,
    identifier: work.ark,
    license: work.rights_statement,
    isAccessibleForFree: work.access_class === "open",
    citation: work.citation.en,
  };

  return (
    <article className="pt-12" lang={locale}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div
          className="frame flex aspect-[3/4] items-center justify-center p-8"
          dir={work.script === "Arab" ? "rtl" : "ltr"}
          lang={work.language === "ara" ? "ar" : "en"}
        >
          {pages[0]?.thumbnail_available ? (
            <p className="label">{t("scanLabel")}</p>
          ) : (
            <p className="reading text-center text-ink-faint">{t("noThumbnail")}</p>
          )}
        </div>
        <header className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <AccessBadge accessClass={work.access_class} />
            <span className="label font-mono">{work.ark}</span>
          </div>
          <h1
            className="text-step-3"
            lang={locale === "ar" ? "ar" : work.title_en ? "en" : "ar"}
            dir={locale === "ar" || !work.title_en ? "rtl" : "ltr"}
          >
            {title}
          </h1>
          {otherTitle ? (
            <p
              className="reading text-ink-muted"
              lang={locale === "ar" ? "en" : "ar"}
              dir={locale === "ar" ? "ltr" : "rtl"}
            >
              {otherTitle}
            </p>
          ) : null}
          <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-[max-content_1fr]">
            <RecordField
              label={t("author", {
                count: work.agents.filter((a) => a.role === "author").length || 1,
              })}
              values={work.agents
                .filter((a) => a.role === "author")
                .map((a) => (locale === "ar" ? a.name_ar : (a.name_latin ?? a.name_ar)))}
            />
            <RecordField
              label={t("published")}
              values={[formatHeritageDate(work.date_edtf, work.date_hijri, locale)]}
            />
            <RecordField
              label={t("language")}
              values={[
                work.language === "ara" ? (locale === "ar" ? "العربية" : "Arabic") : work.language,
              ]}
            />
            <RecordField label={t("extent")} values={[work.extent ?? ""]} />
            <RecordField label={t("subjects")} values={byFacet("subject").map(label)} />
            <RecordField label={t("places")} values={byFacet("place").map(label)} />
            <RecordField label={t("periods")} values={byFacet("period").map(label)} />
            <RecordField label={t("material")} values={byFacet("material").map(label)} />
          </dl>
          <div className="mt-4 flex flex-col gap-3">
            <AccessAction
              locale={locale}
              name={work.public_id}
              signedIn={Boolean(session)}
              canRead={work.can_read}
              canRequest={work.can_request_access}
            />
            <p className="label">
              {work.sample_page_limit === null
                ? ta("allPagesSample")
                : ta("samplePages", { count: Math.min(work.sample_page_limit, work.page_count) })}
            </p>
            <p className="label text-ink-faint">{ta("readerSoon")}</p>
          </div>
        </header>
      </div>

      {description ? (
        <section className="hairline-top mt-section-64 pt-8" aria-labelledby="description">
          <h2 id="description" className="label">
            {t("description")}
          </h2>
          <p
            className="reading mt-3"
            lang={locale === "ar" || !work.description_en ? "ar" : "en"}
            dir={locale === "ar" || !work.description_en ? "rtl" : "ltr"}
          >
            {description}
          </p>
        </section>
      ) : null}

      <section
        className="hairline-top mt-12 pt-8 grid gap-8 sm:grid-cols-2"
        aria-label={t("provenance")}
      >
        <div>
          <h2 className="label">{t("provenance")}</h2>
          <p className="reading mt-3 text-ink-muted">{work.provenance ?? "—"}</p>
        </div>
        <div>
          <h2 className="label">{t("rights")}</h2>
          <p className="mt-3">
            <a
              href={work.rights_statement}
              rel="noopener noreferrer"
              className="font-mono text-step-n1 break-all"
            >
              {work.rights_statement}
            </a>
          </p>
          {work.collections.length > 0 ? (
            <>
              <h2 className="label mt-6">{t("collections")}</h2>
              <ul className="mt-3 flex flex-col gap-1">
                {work.collections.map((c) => (
                  <li key={c.public_id}>
                    <Link href={`/collections/${c.public_id}`}>
                      {locale === "ar" ? c.title_ar : (c.title_en ?? c.title_ar)}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </section>

      <CitationBlock
        locale={locale}
        ark={work.citation.ark}
        text={locale === "ar" ? work.citation.ar : work.citation.en}
        heading={t("citation")}
        copyLabel={t("copyCitation")}
        copiedLabel={t("copied")}
        identifierLabel={t("identifier")}
      />

      {pages.length > 0 ? (
        <section className="hairline-top mt-section-64 pt-8" aria-labelledby="pages">
          <h2 id="pages" className="label">
            {t("pagesTitle")}
          </h2>
          <PageGrid pages={pages} locale={locale} sampleLabel={t("sample")} />
        </section>
      ) : null}

      {content.length > 0 ? (
        <section className="hairline-top mt-section-64 pt-8" aria-labelledby="secondary">
          <h2 id="secondary" className="label">
            {t("secondaryContent")}
          </h2>
          <ul className="mt-6 flex flex-col gap-6">
            {content.map((object) => (
              <li
                key={object.public_id}
                className="frame p-6"
                lang={object.language === "ara" ? "ar" : "en"}
                dir={object.script === "Arab" ? "rtl" : "ltr"}
              >
                <ProvenanceLabel object={object} locale={locale} />
                <p className="reading mt-3 whitespace-pre-line">{object.body}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
