"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { formatNumber } from "@/lib/format";

export type Panel = "contents" | "search" | "print" | "cite" | null;

const BUTTON = "control min-h-10 px-3 text-step-n1 disabled:opacity-40";

export function Toolbar({
  locale,
  pageLabel,
  pageNumber,
  pageCount,
  twoPage,
  panel,
  printable,
  disabled,
  onPrev,
  onNext,
  onFirst,
  onLast,
  onGoTo,
  onZoomIn,
  onZoomOut,
  onFit,
  onRotate,
  onToggleTwoPage,
  onPanel,
}: {
  locale: string;
  pageLabel: string;
  pageNumber: number;
  pageCount: number;
  twoPage: boolean;
  panel: Panel;
  printable: boolean;
  disabled: boolean;
  onPrev: () => void;
  onNext: () => void;
  onFirst: () => void;
  onLast: () => void;
  onGoTo: (seq: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onRotate: () => void;
  onToggleTwoPage: () => void;
  onPanel: (panel: Panel) => void;
}) {
  const t = useTranslations("reader");
  const [draft, setDraft] = useState("");
  const atStart = pageNumber <= 1;
  const atEnd = pageNumber >= pageCount;

  function toggle(name: Exclude<Panel, null>, text: string) {
    const active = panel === name;
    return (
      <button
        type="button"
        className={`${BUTTON} ${active ? "control-primary" : ""}`}
        aria-pressed={active}
        onClick={() => onPanel(active ? null : name)}
        disabled={disabled}
      >
        {text}
      </button>
    );
  }

  return (
    <div
      role="toolbar"
      aria-label={t("toolbar")}
      aria-orientation="horizontal"
      className="reader-toolbar frame mx-auto mb-3 flex max-w-[66rem] flex-wrap items-center justify-center gap-2 bg-surface-raised px-3 py-2"
    >
      <div className="flex flex-wrap items-center gap-1">
        <button type="button" className={BUTTON} onClick={onFirst} disabled={disabled || atStart}>
          {t("first")}
        </button>
        <button type="button" className={BUTTON} onClick={onPrev} disabled={disabled || atStart}>
          {t("previous")}
        </button>
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const seq = Number.parseInt(draft, 10);
            if (Number.isFinite(seq) && seq >= 1) onGoTo(seq);
            setDraft("");
          }}
        >
          <label htmlFor="reader-page" className="sr-only">
            {t("goTo")}
          </label>
          <input
            id="reader-page"
            type="number"
            inputMode="numeric"
            min={1}
            max={pageCount}
            value={draft}
            placeholder={String(pageNumber)}
            onChange={(event) => setDraft(event.target.value)}
            className="control min-h-10 w-20 text-center"
            disabled={disabled}
          />
          <span className="label whitespace-nowrap" aria-live="polite">
            {t("pageOf", { current: pageLabel, total: formatNumber(pageCount, locale) })}
          </span>
        </form>
        <button type="button" className={BUTTON} onClick={onNext} disabled={disabled || atEnd}>
          {t("next")}
        </button>
        <button type="button" className={BUTTON} onClick={onLast} disabled={disabled || atEnd}>
          {t("last")}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          className={BUTTON}
          onClick={onZoomOut}
          disabled={disabled}
          aria-label={t("zoomOut")}
        >
          −
        </button>
        <button
          type="button"
          className={BUTTON}
          onClick={onZoomIn}
          disabled={disabled}
          aria-label={t("zoomIn")}
        >
          +
        </button>
        <button type="button" className={BUTTON} onClick={onFit} disabled={disabled}>
          {t("fit")}
        </button>
        <button type="button" className={BUTTON} onClick={onRotate} disabled={disabled}>
          {t("rotate")}
        </button>
        <button
          type="button"
          className={`${BUTTON} ${twoPage ? "control-primary" : ""}`}
          aria-pressed={twoPage}
          onClick={onToggleTwoPage}
          disabled={disabled}
        >
          {twoPage ? t("singlePage") : t("twoPage")}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {toggle("contents", t("contents"))}
        {toggle("search", t("search"))}
        {printable ? toggle("print", t("print")) : null}
        {toggle("cite", t("cite"))}
      </div>
    </div>
  );
}
