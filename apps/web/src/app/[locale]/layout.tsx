import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { direction, resolveLocale } from "@/i18n/routing";
import { currentSession } from "@/lib/session";

import { fontClassName } from "../fonts";
import "../globals.css";

// Every page is rendered per request: the Content Security Policy nonce (SEC-16), the signed-in
// state and the catalog's access decisions all depend on the request, never on build time.
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const locale = resolveLocale((await params).locale);
  const t = await getTranslations({ locale, namespace: "meta" });
  const brand = await getTranslations({ locale, namespace: "brand" });
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:8080";
  return {
    metadataBase: new URL(base),
    title: { default: brand("name"), template: `%s — ${brand("name")}` },
    description: t("description"),
    alternates: { languages: { ar: "/ar", en: "/en", "x-default": "/ar" } },
    openGraph: {
      siteName: brand("name"),
      locale: locale === "ar" ? "ar_JO" : "en_GB",
      type: "website",
    },
    robots: { index: true, follow: true },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const locale = resolveLocale((await params).locale);
  setRequestLocale(locale);
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const session = await currentSession().catch(() => null);
  const t = await getTranslations({ locale, namespace: "nav" });

  return (
    <html lang={locale} dir={direction(locale)} className={fontClassName} suppressHydrationWarning>
      <head>
        <meta name="color-scheme" content="light dark" />
        {nonce ? <meta property="csp-nonce" content={nonce} /> : null}
      </head>
      <body className="flex min-h-dvh flex-col bg-background text-ink">
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-50 focus:bg-surface-raised focus:px-3 focus:py-2"
        >
          {t("skipToContent")}
        </a>
        <NextIntlClientProvider>
          <SiteHeader
            locale={locale}
            signedIn={Boolean(session)}
            roles={session?.data.roles ?? []}
          />
          <main
            id="content"
            className="mx-auto w-full max-w-[80rem] flex-1 px-4 pb-section-64 sm:px-6 lg:px-8"
          >
            {children}
          </main>
          <SiteFooter locale={locale} />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
