"use client";

import { Link, usePathname } from "@/i18n/routing";

export function LocaleSwitcher({ locale, label }: { locale: string; label: string }) {
  const pathname = usePathname();
  const other = locale === "ar" ? "en" : "ar";
  return (
    <Link
      href={pathname}
      locale={other}
      lang={other}
      dir={other === "ar" ? "rtl" : "ltr"}
      className="font-interface"
    >
      {label}
    </Link>
  );
}
