import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <div className="pt-section-64">
      <h1 className="text-step-3">{t("notFoundTitle")}</h1>
      <p className="reading mt-4 text-ink-muted">{t("notFound")}</p>
      <p className="mt-8">
        <Link href="/">{t("backHome")}</Link>
      </p>
    </div>
  );
}
