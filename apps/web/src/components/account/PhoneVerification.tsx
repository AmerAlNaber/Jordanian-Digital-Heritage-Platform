"use client";

import type { PhoneStatus } from "@jdhp/schemas";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

type ErrorKey = "invalidNumber" | "codeInvalid" | "sendLimited" | "generic";

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

async function errorKeyFor(response: Response): Promise<ErrorKey> {
  if (response.status === 422) return "invalidNumber";
  try {
    const problem = (await response.json()) as { code?: string };
    if (problem.code === "phone_code_invalid") return "codeInvalid";
    if (problem.code === "phone_send_limited") return "sendLimited";
  } catch {
    return "generic";
  }
  return "generic";
}

/** Phone verification: a number, a six-digit code, and the member's level rises (ACC-1). */
export function PhoneVerification({ status, locale }: { status: PhoneStatus; locale: string }) {
  const t = useTranslations("account.phone");
  const router = useRouter();
  const [number, setNumber] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"number" | "code">(status.pending ? "code" : "number");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [changing, setChanging] = useState(false);

  const verified = status.verified_at !== null && status.verified_at !== undefined;
  const verifiedOn = verified
    ? new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", { dateStyle: "long" }).format(
        new Date(status.verified_at as string),
      )
    : null;

  async function sendCode(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await post("/api/bff/me/phone", { phone_number: number.trim() });
    setBusy(false);
    if (!response.ok) {
      setError(await errorKeyFor(response));
      return;
    }
    setStep("code");
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await post("/api/bff/me/phone/verify", { code: code.trim() });
    setBusy(false);
    if (!response.ok) {
      setError(await errorKeyFor(response));
      return;
    }
    setCode("");
    setChanging(false);
    setStep("number");
    router.refresh();
  }

  return (
    <section aria-labelledby="account-phone" className="mt-12">
      <h2 id="account-phone" className="text-step-2">
        {t("title")}
      </h2>
      <p className="reading mt-3 text-ink-muted">{t("intro")}</p>
      {verified && !changing && step === "number" ? (
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <p className="m-0">
            <span className="label me-2">{t("verifiedNumber")}</span>
            <span dir="ltr" className="font-mono">
              {status.phone_number}
            </span>
            {verifiedOn ? (
              <span className="ms-2 text-ink-muted">{t("since", { date: verifiedOn })}</span>
            ) : null}
          </p>
          <button type="button" className="control" onClick={() => setChanging(true)}>
            {t("change")}
          </button>
        </div>
      ) : null}
      {(!verified || changing) && step === "number" ? (
        <form onSubmit={sendCode} className="mt-6 flex flex-wrap items-end gap-3">
          <label className="grid gap-1">
            <span className="label">{t("numberLabel")}</span>
            <input
              name="phone_number"
              type="tel"
              inputMode="tel"
              dir="ltr"
              autoComplete="tel"
              required
              placeholder="+962 7X XXX XXXX"
              value={number}
              onChange={(event) => setNumber(event.target.value.replace(/[\s-]/g, ""))}
              className="control font-mono"
            />
          </label>
          <button type="submit" className="control control-primary" disabled={busy}>
            {t("sendCode")}
          </button>
          {changing ? (
            <button type="button" className="control" onClick={() => setChanging(false)}>
              {t("cancel")}
            </button>
          ) : null}
        </form>
      ) : null}
      {step === "code" ? (
        <form onSubmit={confirm} className="mt-6 flex flex-wrap items-end gap-3">
          <p className="m-0 basis-full text-ink-muted">
            {t("codeSent", { number: status.phone_number ?? number })}
          </p>
          <label className="grid gap-1">
            <span className="label">{t("codeLabel")}</span>
            <input
              name="code"
              inputMode="numeric"
              dir="ltr"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              required
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              className="control font-mono tracking-widest"
            />
          </label>
          <button
            type="submit"
            className="control control-primary"
            disabled={busy || code.length !== 6}
          >
            {t("confirm")}
          </button>
          <button type="button" className="control" onClick={() => setStep("number")}>
            {t("otherNumber")}
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-step-n1 text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}
    </section>
  );
}
