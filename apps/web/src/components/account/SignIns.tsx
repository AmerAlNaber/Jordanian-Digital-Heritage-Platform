"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { SignInView } from "@/lib/sign-ins";

function when(value: string | null, locale: string): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

/** Every sign-in and every open reader, each with a way to end it (SEC-5). */
export function SignIns({ signIns, locale }: { signIns: SignInView[]; locale: string }) {
  const t = useTranslations("account.sessions");
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function end(path: string, key: string) {
    setBusy(key);
    setFailed(false);
    const response = await fetch(path, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    setBusy(null);
    if (!response.ok) {
      setFailed(true);
      return;
    }
    router.refresh();
  }

  return (
    <section aria-labelledby="account-sessions" className="mt-12">
      <h2 id="account-sessions" className="text-step-2">
        {t("title")}
      </h2>
      <p className="reading mt-3 text-ink-muted">{t("intro")}</p>
      {signIns.length === 0 ? <p className="mt-6 text-ink-muted">{t("none")}</p> : null}
      <ul className="mt-6 grid list-none gap-4 p-0">
        {signIns.map((signIn) => {
          const key = signIn.id ?? "orphans";
          return (
            <li key={key} className="hairline-start ps-4">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="font-medium">
                  {signIn.id === null
                    ? t("earlierSignIn")
                    : (signIn.browser ?? t("unknownBrowser"))}
                </span>
                {signIn.current ? <span className="label">{t("thisDevice")}</span> : null}
                {signIn.ipAddress ? (
                  <span dir="ltr" className="font-mono text-step-n1 text-ink-muted">
                    {signIn.ipAddress}
                  </span>
                ) : null}
                {signIn.lastAccessAt ? (
                  <span className="text-step-n1 text-ink-muted">
                    {t("lastSeen", { time: when(signIn.lastAccessAt, locale) ?? "" })}
                  </span>
                ) : null}
                {signIn.id !== null && !signIn.current ? (
                  <button
                    type="button"
                    className="control ms-auto"
                    disabled={busy !== null}
                    onClick={() =>
                      end(`/api/bff/me/sign-ins/${encodeURIComponent(signIn.id ?? "")}`, key)
                    }
                  >
                    {t("endSignIn")}
                  </button>
                ) : null}
              </div>
              {signIn.readers.length > 0 ? (
                <ul className="mt-2 grid list-none gap-2 p-0">
                  {signIn.readers.map((reader) => (
                    <li
                      key={reader.public_id}
                      className="flex flex-wrap items-baseline gap-x-3 text-step-n1"
                    >
                      <span>
                        {t("reading", {
                          title:
                            locale === "ar"
                              ? reader.title_ar
                              : (reader.title_en ?? reader.title_ar),
                        })}
                      </span>
                      <span className="text-ink-muted">
                        {t("lastSeen", { time: when(reader.last_seen_at, locale) ?? "" })}
                      </span>
                      <button
                        type="button"
                        className="underline decoration-hairline-strong underline-offset-4 hover:decoration-accent"
                        disabled={busy !== null}
                        onClick={() =>
                          end(
                            `/api/bff/me/sessions/${encodeURIComponent(reader.public_id)}`,
                            reader.public_id,
                          )
                        }
                      >
                        {t("endReader")}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
      {failed ? (
        <p role="alert" className="mt-3 text-step-n1 text-danger">
          {t("failed")}
        </p>
      ) : null}
    </section>
  );
}
