"use client";

import type { PageHit } from "@jdhp/schemas";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { formatNumber } from "@/lib/format";
import { searchInWork } from "@/lib/reader-client";

/** Search inside the book: matches are pages and highlight boxes, never text (RDR-3, CAT-4). */
export function SearchPanel({
  locale,
  work,
  initialQuery,
  onResults,
  onSelect,
}: {
  locale: string;
  work: string;
  initialQuery: string;
  onResults: (hits: PageHit[]) => void;
  onSelect: (seq: number) => void;
}) {
  const t = useTranslations("reader");
  const [query, setQuery] = useState(initialQuery);
  const [hits, setHits] = useState<PageHit[] | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setBusy(true);
      try {
        const result = await searchInWork(work, trimmed);
        const pages = result.works[0]?.pages ?? [];
        setHits(pages);
        onResults(pages);
      } catch {
        setHits([]);
        onResults([]);
      } finally {
        setBusy(false);
      }
    },
    [work, onResults],
  );

  useEffect(() => {
    if (initialQuery) void run(initialQuery);
  }, [initialQuery, run]);

  return (
    <div className="flex flex-col gap-4">
      <form
        role="search"
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void run(query);
        }}
      >
        <label htmlFor="reader-search" className="sr-only">
          {t("search")}
        </label>
        <input
          id="reader-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("searchPlaceholder")}
          className="control min-h-10 flex-1"
          dir="auto"
          autoComplete="off"
        />
        <button type="submit" className="control control-primary min-h-10" disabled={busy}>
          {t("search")}
        </button>
      </form>
      {busy ? <p className="label">{t("searching")}</p> : null}
      {hits !== null && !busy ? (
        <section aria-live="polite">
          <p className="label hairline-bottom pb-2">{t("matches", { count: hits.length })}</p>
          {hits.length === 0 ? (
            <p className="reading mt-3 text-ink-muted">{t("noMatches")}</p>
          ) : (
            <ol className="mt-2 flex flex-col">
              {hits.map((hit) => (
                <li key={hit.seq}>
                  <button
                    type="button"
                    onClick={() => onSelect(hit.seq)}
                    className="flex w-full items-baseline justify-between gap-3 py-2 text-start hover:underline"
                    disabled={!hit.scan_visible}
                  >
                    <span>{t("page", { label: hit.label ?? formatNumber(hit.seq, locale) })}</span>
                    <span className="label">{t("highlights", { count: hit.regions.length })}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
      ) : null}
    </div>
  );
}
