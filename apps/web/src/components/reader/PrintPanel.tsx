"use client";

import type { PrintJobOut, ReaderSessionOut } from "@jdhp/schemas";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ReaderError, printLink, printStatus, requestPrint } from "@/lib/reader-client";

type Phase =
  | { kind: "idle" }
  | { kind: "preparing"; job: PrintJobOut }
  | { kind: "ready"; job: PrintJobOut; url: string }
  | { kind: "error"; code: ErrorCode };

type ErrorCode =
  | "print_quota_exceeded"
  | "print_pages_invalid"
  | "print_not_ready"
  | "failed"
  | "forbidden"
  | "generic";

const POLL_MS = 2000;
const POLL_LIMIT = 60;

function errorCode(error: unknown): ErrorCode {
  if (error instanceof ReaderError) {
    const code = error.problem.code;
    if (code === "print_quota_exceeded" || code === "print_pages_invalid") return code;
    if (code === "print_not_ready") return code;
    if (error.status === 403) return "forbidden";
  }
  return "generic";
}

/** Print: a server-rendered, marked, low-resolution PDF within the grant's quota (RDR-4). */
export function PrintPanel({
  session,
  currentSeq,
  pageCount,
}: {
  session: ReaderSessionOut;
  currentSeq: number;
  pageCount: number;
}) {
  const t = useTranslations("print");
  const [mode, setMode] = useState<"current" | "range">("current");
  const [from, setFrom] = useState(String(currentSeq));
  const [to, setTo] = useState(String(Math.min(pageCount, currentSeq + 1)));
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [quota, setQuota] = useState<number | null>(null);
  const polls = useRef(0);

  const pages =
    mode === "current"
      ? [currentSeq]
      : range(Number.parseInt(from, 10), Number.parseInt(to, 10), pageCount);

  useEffect(() => {
    if (phase.kind !== "preparing") return;
    const job = phase.job;
    const timer = window.setTimeout(async () => {
      polls.current += 1;
      try {
        const status = await printStatus(job.public_id);
        setQuota(status.quota_remaining);
        if (status.state === "ready") {
          const link = await printLink(job.public_id);
          setPhase({ kind: "ready", job: status, url: link.url });
        } else if (status.state === "failed" || polls.current > POLL_LIMIT) {
          setPhase({ kind: "error", code: "failed" });
        } else {
          setPhase({ kind: "preparing", job: status });
        }
      } catch (error) {
        setPhase({ kind: "error", code: errorCode(error) });
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [phase]);

  async function submit() {
    if (pages.length === 0) {
      setPhase({ kind: "error", code: "print_pages_invalid" });
      return;
    }
    polls.current = 0;
    try {
      const job = await requestPrint(session, pages);
      setQuota(job.quota_remaining);
      setPhase({ kind: "preparing", job });
    } catch (error) {
      if (error instanceof ReaderError && typeof error.problem.quota_remaining === "number") {
        setQuota(error.problem.quota_remaining);
      }
      setPhase({ kind: "error", code: errorCode(error) });
    }
  }

  const busy = phase.kind === "preparing";
  return (
    <div className="flex flex-col gap-4">
      <p className="reading text-step-n1 text-ink-muted">{t("intro")}</p>
      {quota !== null ? <p className="label">{t("quota", { count: quota })}</p> : null}
      <fieldset className="flex flex-col gap-3" disabled={busy}>
        <legend className="sr-only">{t("title")}</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="print-mode"
            checked={mode === "current"}
            onChange={() => setMode("current")}
          />
          {t("currentPage")}
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="print-mode"
            checked={mode === "range"}
            onChange={() => setMode("range")}
          />
          {t("range")}
        </label>
        {mode === "range" ? (
          <div className="flex items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="label">{t("from")}</span>
              <input
                type="number"
                min={1}
                max={pageCount}
                value={from}
                onChange={(event) => setFrom(event.target.value)}
                className="control min-h-10 w-24 text-center"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="label">{t("to")}</span>
              <input
                type="number"
                min={1}
                max={pageCount}
                value={to}
                onChange={(event) => setTo(event.target.value)}
                className="control min-h-10 w-24 text-center"
              />
            </label>
          </div>
        ) : null}
        <p className="label">{t("pagesSelected", { count: pages.length })}</p>
      </fieldset>
      {phase.kind === "ready" ? (
        <div className="frame flex flex-col gap-2 p-4" aria-live="polite">
          <p>{t("ready")}</p>
          <a
            href={phase.url}
            className="control control-primary inline-flex w-fit items-center no-underline"
            rel="noopener"
          >
            {t("download")}
          </a>
          <p className="label">{t("downloadNote")}</p>
        </div>
      ) : (
        <button
          type="button"
          className="control control-primary min-h-10 w-fit"
          onClick={() => void submit()}
          disabled={busy}
        >
          {busy ? t("preparing") : t("submit")}
        </button>
      )}
      {phase.kind === "error" ? (
        <p className="text-warning" role="alert">
          {t(`errors.${phase.code}`)}
        </p>
      ) : null}
    </div>
  );
}

function range(from: number, to: number, count: number): number[] {
  if (!Number.isFinite(from) || !Number.isFinite(to)) return [];
  const start = Math.max(1, Math.min(from, to));
  const end = Math.min(count, Math.max(from, to));
  if (end < start) return [];
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}
