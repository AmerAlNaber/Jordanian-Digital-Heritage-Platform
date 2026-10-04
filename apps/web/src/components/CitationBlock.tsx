"use client";

import { useState } from "react";

export function CitationBlock({
  locale,
  ark,
  text,
  heading,
  copyLabel,
  copiedLabel,
  identifierLabel,
}: {
  locale: string;
  ark: string;
  text: string;
  heading: string;
  copyLabel: string;
  copiedLabel: string;
  identifierLabel: string;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }
  return (
    <section className="hairline-top mt-12 pt-8" aria-labelledby="citation">
      <h2 id="citation" className="label">
        {heading}
      </h2>
      <blockquote className="reading mt-3" lang={locale} cite={ark}>
        {text}
      </blockquote>
      <dl className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <dt className="label">{identifierLabel}</dt>
        <dd className="font-mono text-step-n1" data-testid="ark">
          {ark}
        </dd>
      </dl>
      <button type="button" onClick={copy} className="control mt-4" aria-live="polite">
        {copied ? copiedLabel : copyLabel}
      </button>
    </section>
  );
}
