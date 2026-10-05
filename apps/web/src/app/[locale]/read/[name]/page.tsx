import type { PageSummary, WorkDetail } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { ReaderMount } from "@/components/reader/ReaderMount";
import { parsePageParam } from "@/components/reader/model";
import { Link, resolveLocale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api";
import { currentSession } from "@/lib/session";

type Params = Promise<{ locale: string; name: string }>;
type Search = Promise<{ page?: string | string[]; q?: string | string[] }>;

const RTL_SCRIPTS = new Set(["Arab", "Hebr", "Syrc"]);
const PRINTABLE_CLASSES = new Set(["open", "registered", "paid"]);

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
  const t = await getTranslations({ locale, namespace: "reader" });
  const title = work
    ? locale === "ar"
      ? work.title_ar
      : (work.title_en ?? work.title_translit ?? work.title_ar)
    : t("title");
  return { title: `${t("title")} — ${title}`, robots: { index: false, follow: false } };
}

/** The secure reader. The scan is the page; nothing here is text from the book (RDR-1, CAT-4). */
export default async function ReadPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}) {
  const { locale: requestedLocale, name } = await params;
  const locale = resolveLocale(requestedLocale);
  setRequestLocale(locale);
  const work = await loadWork(name, locale);
  if (!work) notFound();
  const t = await getTranslations("reader");
  const session = await currentSession().catch(() => null);
  const title =
    locale === "ar" ? work.title_ar : (work.title_en ?? work.title_translit ?? work.title_ar);

  if (!work.can_read) {
    return (
      <div className="pt-12">
        <h1 className="text-step-3">{title}</h1>
        <p className="reading mt-6 text-ink-muted">{session ? t("noAccess") : t("signInToRead")}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          {session ? null : (
            <a
              href={`/api/auth/login?return=/${locale}/read/${work.public_id}`}
              className="control control-primary inline-flex items-center"
            >
              {t("signInToRead")}
            </a>
          )}
          <Link href={`/works/${work.public_id}`} className="control inline-flex items-center no-underline">
            {t("backToRecord")}
          </Link>
        </div>
      </div>
    );
  }

  const search = await searchParams;
  const pages = await apiFetch<PageSummary[]>(`/works/${encodeURIComponent(name)}/pages`, {
    locale,
  });
  const info = pages.map((page) => ({
    seq: page.seq,
    label: page.label,
    sectionTitle: page.section_title,
    width: page.width_px,
    height: page.height_px,
    inSampleRange: page.in_sample_range,
  }));
  const query = (Array.isArray(search.q) ? search.q[0] : search.q) ?? "";
  return (
    <ReaderMount
      locale={locale}
      work={{
        publicId: work.public_id,
        title,
        ark: work.ark,
        citation: locale === "ar" ? work.citation.ar : work.citation.en,
        samplePageLimit: work.sample_page_limit,
        rtl: RTL_SCRIPTS.has(work.script),
        printable: PRINTABLE_CLASSES.has(work.access_class),
      }}
      pages={info}
      initialIndex={parsePageParam(search.page, info.length)}
      initialQuery={query.slice(0, 200)}
      signedIn={Boolean(session)}
    />
  );
}
