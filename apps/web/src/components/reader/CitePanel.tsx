"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

export function CitePanel({ locale, text, ark }: { locale: string; text: string; ark: string }) {
  const t = useTranslations("work");
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="flex flex-col gap-3">
      <blockquote className="reading" lang={locale} cite={ark}>
        {text}
      </blockquote>
      <p className="label font-mono break-all">{ark}</p>
      <button type="button" onClick={() => void copy()} className="control min-h-10 w-fit" aria-live="polite">
        {copied ? t("copied") : t("copyCitation")}
      </button>
    </div>
  );
}
