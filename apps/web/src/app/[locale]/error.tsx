"use client";

import { useTranslations } from "next-intl";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errors");
  return (
    <div className="pt-section-64">
      <h1 className="text-step-3">{t("genericTitle")}</h1>
      <p className="reading mt-4 text-ink-muted">{t("generic")}</p>
      <button type="button" onClick={reset} className="control mt-8">
        ↻
      </button>
    </div>
  );
}
