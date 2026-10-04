import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";

export async function Facets({
  classes,
  selected,
  query,
}: {
  locale: string;
  classes: readonly string[];
  selected?: string;
  query?: string;
}) {
  const t = await getTranslations("catalog");
  const ta = await getTranslations("access");
  const base = query ? { q: query } : {};
  return (
    <aside aria-label={t("filters")} className="font-interface text-step-n1">
      <h2 className="label hairline-bottom pb-3">{t("accessClass")}</h2>
      <ul className="mt-3 flex flex-col gap-2">
        <li>
          <Link
            href={{ pathname: "/catalog", query: base }}
            aria-current={selected ? undefined : "true"}
            className={selected ? "" : "font-medium"}
          >
            {t("allClasses")}
          </Link>
        </li>
        {classes.map((cls) => (
          <li key={cls}>
            <Link
              href={{ pathname: "/catalog", query: { ...base, access_class: cls } }}
              aria-current={selected === cls ? "true" : undefined}
              className={selected === cls ? "font-medium" : ""}
            >
              {ta(cls as "open" | "registered" | "paid" | "restricted")}
            </Link>
          </li>
        ))}
      </ul>
      {selected || query ? (
        <p className="mt-4">
          <Link href="/catalog">{t("clear")}</Link>
        </p>
      ) : null}
    </aside>
  );
}
