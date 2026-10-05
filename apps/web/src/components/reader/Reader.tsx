"use client";

import type { PageHit, ReaderSessionOut, Region } from "@jdhp/schemas";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Link } from "@/i18n/routing";
import { formatNumber } from "@/lib/format";
import { endSession, heartbeat, openSession } from "@/lib/reader-client";

import { CitePanel } from "./CitePanel";
import { ContentsPanel } from "./ContentsPanel";
import { EndedNotice } from "./EndedNotice";
import {
  type EndedReason,
  type PageInfo,
  clampIndex,
  endedReasonFrom,
  layoutFor,
  overlayRects,
  step,
} from "./model";
import { PrintPanel } from "./PrintPanel";
import { SearchPanel } from "./SearchPanel";
import { type Panel, Toolbar } from "./Toolbar";
import { Viewer, type ViewerApi } from "./Viewer";

export type ReaderWork = {
  publicId: string;
  title: string;
  ark: string;
  citation: string;
  samplePageLimit: number | null;
  rtl: boolean;
  printable: boolean;
};

const EMPTY_PAGE: PageInfo = {
  seq: 1,
  label: null,
  sectionTitle: null,
  width: null,
  height: null,
  inSampleRange: true,
};

type Status =
  | { kind: "opening" }
  | { kind: "active"; session: ReaderSessionOut }
  | { kind: "ended"; reason: EndedReason };

/**
 * The secure reader (RDR-1, RDR-3, RDR-5, RDR-6). A session is opened through the
 * backend-for-frontend, the heartbeat re-validates it and refreshes both credentials every
 * minute while reporting the pages read, and the viewer blanks with the reason when it ends.
 */
export function Reader({
  locale,
  work,
  pages,
  initialIndex,
  initialQuery,
  signedIn,
}: {
  locale: string;
  work: ReaderWork;
  pages: PageInfo[];
  initialIndex: number;
  initialQuery: string;
  signedIn: boolean;
}) {
  const t = useTranslations("reader");
  const [status, setStatus] = useState<Status>({ kind: "opening" });
  const [index, setIndex] = useState(() => clampIndex(initialIndex, pages.length));
  const [twoPage, setTwoPage] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [panel, setPanel] = useState<Panel>(initialQuery ? "search" : null);
  const [highlights, setHighlights] = useState<Record<number, Region[]>>({});
  const session = useRef<ReaderSessionOut | null>(null);
  const viewed = useRef<Set<number>>(new Set());
  const lastBeat = useRef(Date.now());
  const api = useRef<ViewerApi | null>(null);
  const onApi = useCallback((value: ViewerApi | null) => {
    api.current = value;
  }, []);

  const mounted = useRef(false);
  const open = useCallback(async () => {
    setStatus({ kind: "opening" });
    try {
      const opened = await openSession(work.publicId);
      if (!mounted.current) {
        endSession(opened); // resolved after the reader went away: close it at once
        return;
      }
      session.current = opened;
      lastBeat.current = Date.now();
      setStatus({ kind: "active", session: opened });
    } catch (error) {
      if (!mounted.current) return;
      session.current = null;
      setStatus({ kind: "ended", reason: endedReasonFrom(error) });
    }
  }, [work.publicId]);

  useEffect(() => {
    mounted.current = true;
    void open();
    const close = () => {
      if (session.current) endSession(session.current);
      session.current = null;
    };
    window.addEventListener("pagehide", close);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", close);
      close();
    };
  }, [open]);

  const sessionId = status.kind === "active" ? status.session.public_id : null;
  const interval = status.kind === "active" ? status.session.heartbeat_interval_seconds : 60;
  useEffect(() => {
    if (!sessionId) return;
    const timer = window.setInterval(async () => {
      const current = session.current;
      if (!current) return;
      const now = Date.now();
      const dwell = (now - lastBeat.current) / 1000;
      lastBeat.current = now;
      const seen = [...viewed.current];
      viewed.current.clear();
      try {
        const refreshed = await heartbeat(current, seen, dwell);
        session.current = refreshed;
        setStatus({ kind: "active", session: refreshed });
      } catch (error) {
        session.current = null;
        setStatus({ kind: "ended", reason: endedReasonFrom(error) });
      }
    }, interval * 1000);
    return () => window.clearInterval(timer);
  }, [sessionId, interval]);

  const layout = useMemo(
    () => layoutFor(work.publicId, pages, index, twoPage, work.rtl),
    [work.publicId, pages, index, twoPage, work.rtl],
  );
  const currentSeqs = layout.sources.map((source) => source.seq);
  const current: PageInfo = pages[clampIndex(index, pages.length)] ?? EMPTY_PAGE;

  useEffect(() => {
    for (const seq of currentSeqs) viewed.current.add(seq);
    const url = new URL(window.location.href);
    url.searchParams.set("page", String(current.seq));
    window.history.replaceState(null, "", url);
    // currentSeqs is derived from index and twoPage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, twoPage]);

  const overlays = useMemo(
    () =>
      layout.sources.flatMap((source) => {
        const page = pages.find((p) => p.seq === source.seq);
        return overlayRects(highlights[source.seq] ?? [], source, page?.width ?? null);
      }),
    [layout, highlights, pages],
  );

  const goTo = useCallback(
    (seq: number) => {
      const position = pages.findIndex((page) => page.seq === seq);
      if (position >= 0) setIndex(position);
    },
    [pages],
  );
  const onResults = useCallback(
    (hits: PageHit[]) => {
      const next: Record<number, Region[]> = {};
      for (const hit of hits) next[hit.seq] = hit.regions;
      setHighlights(next);
      const first = hits.find((hit) => hit.scan_visible);
      if (first) goTo(first.seq);
    },
    [goTo],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const count = pages.length;
      switch (event.key) {
        case "PageDown":
        case "]":
          setIndex((i) => step(i, count, twoPage, 1));
          break;
        case "PageUp":
        case "[":
          setIndex((i) => step(i, count, twoPage, -1));
          break;
        case "Home":
          setIndex(0);
          break;
        case "End":
          setIndex(count - 1);
          break;
        case "+":
        case "=":
          api.current?.zoomIn();
          break;
        case "-":
          api.current?.zoomOut();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pages.length, twoPage]);

  const active = status.kind === "active";
  const pageLabel = current.label ?? formatNumber(current.seq, locale);

  return (
    <div
      className="-mx-4 flex flex-col sm:-mx-6 lg:-mx-8"
      style={{ blockSize: "calc(100dvh - 6.5rem)" }}
    >
      <div className="hairline-bottom flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-2 text-step-n1 sm:px-6 lg:px-8">
        <Link href={`/works/${work.publicId}`}>{t("backToRecord")}</Link>
        <span className="truncate font-arabic-display text-step-0" lang={work.rtl ? "ar" : "en"}>
          {work.title}
        </span>
        <span className="label hidden md:inline">{t("markNotice")}</span>
      </div>
      <div className="relative flex min-h-0 flex-1">
        <div className="relative min-h-0 flex-1 bg-surface" aria-busy={status.kind === "opening"}>
          {status.kind === "opening" ? (
            <p className="label absolute inset-0 flex items-center justify-center">{t("opening")}</p>
          ) : null}
          {active ? (
            <Viewer
              sources={layout.sources}
              overlays={overlays}
              rotation={rotation}
              tileToken={status.session.tokens?.tile_token ?? ""}
              label={t("viewerLabel", { title: work.title })}
              onApi={onApi}
            />
          ) : null}
          {status.kind === "ended" ? (
            <EndedNotice
              locale={locale}
              work={work.publicId}
              reason={status.reason}
              signedIn={signedIn}
              onReopen={() => void open()}
            />
          ) : null}
        </div>
        {panel && active ? (
          <aside
            className="hairline-start w-[22rem] max-w-[45vw] overflow-y-auto bg-background p-4"
            aria-label={
              panel === "contents"
                ? t("contents")
                : panel === "search"
                  ? t("search")
                  : panel === "print"
                    ? t("print")
                    : t("cite")
            }
          >
            <div className="mb-3 flex justify-end">
              <button type="button" className="control min-h-10 text-step-n1" onClick={() => setPanel(null)}>
                {t("panelClose")}
              </button>
            </div>
            {panel === "contents" ? (
              <ContentsPanel locale={locale} pages={pages} currentSeqs={currentSeqs} onSelect={goTo} />
            ) : null}
            {panel === "search" ? (
              <SearchPanel
                locale={locale}
                work={work.publicId}
                initialQuery={initialQuery}
                onResults={onResults}
                onSelect={goTo}
              />
            ) : null}
            {panel === "print" && status.kind === "active" ? (
              <PrintPanel session={status.session} currentSeq={current.seq} pageCount={pages.length} />
            ) : null}
            {panel === "cite" ? <CitePanel locale={locale} text={work.citation} ark={work.ark} /> : null}
          </aside>
        ) : null}
      </div>
      <div className="px-4 pt-3 sm:px-6 lg:px-8">
        <Toolbar
          locale={locale}
          pageLabel={pageLabel}
          pageNumber={current.seq}
          pageCount={pages.length}
          twoPage={twoPage}
          panel={panel}
          printable={work.printable && Boolean(status.kind === "active" && status.session.grant)}
          disabled={!active}
          onPrev={() => setIndex((i) => step(i, pages.length, twoPage, -1))}
          onNext={() => setIndex((i) => step(i, pages.length, twoPage, 1))}
          onFirst={() => setIndex(0)}
          onLast={() => setIndex(pages.length - 1)}
          onGoTo={goTo}
          onZoomIn={() => api.current?.zoomIn()}
          onZoomOut={() => api.current?.zoomOut()}
          onFit={() => api.current?.fit()}
          onRotate={() => setRotation((r) => (r + 90) % 360)}
          onToggleTwoPage={() => setTwoPage((v) => !v)}
          onPanel={setPanel}
        />
        <p className="label pb-2 text-center text-step-n2">{t("keyboard")}</p>
      </div>
    </div>
  );
}
