"use client";

import { useTranslations } from "next-intl";

import { Link } from "@/i18n/routing";

import type { EndedReason } from "./model";

/** The reader blanks and says why (RDR-5). The scan is gone; only the reason remains. */
export function EndedNotice({
  locale,
  work,
  reason,
  signedIn,
  onReopen,
}: {
  locale: string;
  work: string;
  reason: EndedReason;
  signedIn: boolean;
  onReopen: () => void;
}) {
  const t = useTranslations("reader");
  const needsSignIn = reason === "unauthorized" || (reason === "grant_required" && !signedIn);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center" role="alert">
      <h2 className="text-step-2">{t("endedTitle")}</h2>
      <p className="reading text-ink-muted">{t(`ended.${reason}`)}</p>
      <div className="flex flex-wrap justify-center gap-3">
        {needsSignIn ? (
          <a
            href={`/api/auth/login?return=/${locale}/read/${work}`}
            className="control control-primary inline-flex items-center"
          >
            {t("signInToRead")}
          </a>
        ) : (
          <button type="button" className="control control-primary" onClick={onReopen}>
            {t("reopen")}
          </button>
        )}
        <Link href={`/works/${work}`} className="control inline-flex items-center no-underline">
          {t("backToRecord")}
        </Link>
      </div>
    </div>
  );
}
