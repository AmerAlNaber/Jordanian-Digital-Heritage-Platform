import type { Me } from "@jdhp/schemas";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { apiFetch } from "@/lib/api";
import { currentSession } from "@/lib/session";
import { resolveLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("title"), robots: { index: false } };
}

export default async function AccountPage({ params }: { params: Promise<{ locale: string }> }) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const t = await getTranslations("account");
  const nav = await getTranslations("nav");
  const session = await currentSession().catch(() => null);
  if (!session) {
    return (
      <div className="pt-12">
        <h1 className="text-step-3">{t("title")}</h1>
        <p className="reading mt-6 text-ink-muted">{t("notSignedIn")}</p>
        <a
          href={`/api/auth/login?return=/${locale}/account`}
          className="control control-primary mt-6 inline-flex w-fit"
        >
          {nav("signIn")}
        </a>
      </div>
    );
  }
  const me = await apiFetch<Me>("/me", { locale });
  const roleKey = me.role as keyof IntlMessages["account"]["roles"];
  const verificationKey = me.verification_level as keyof IntlMessages["account"]["verifications"];
  return (
    <div className="pt-12">
      <h1 className="text-step-3">{t("title")}</h1>
      <dl className="mt-8 grid gap-x-8 gap-y-3 sm:grid-cols-[max-content_1fr]">
        <dt className="label">{t("signedInAs")}</dt>
        <dd className="m-0">{me.display_name ?? me.email ?? me.subject}</dd>
        <dt className="label">{t("role")}</dt>
        <dd className="m-0">{t(`roles.${roleKey}`)}</dd>
        <dt className="label">{t("verification")}</dt>
        <dd className="m-0">{t(`verifications.${verificationKey}`)}</dd>
        <dt className="label">{t("mfa")}</dt>
        <dd className="m-0">{me.mfa ? t("mfaOn") : t("mfaOff")}</dd>
        <dt className="label">{t("preferences")}</dt>
        <dd className="m-0 font-mono text-step-n1">{JSON.stringify(me.preferences)}</dd>
      </dl>
    </div>
  );
}
