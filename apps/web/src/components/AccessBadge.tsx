import { useTranslations } from "next-intl";

export function AccessBadge({ accessClass }: { accessClass: string }) {
  const t = useTranslations("access");
  const key = (
    ["open", "registered", "paid", "restricted", "embargoed"].includes(accessClass)
      ? accessClass
      : "registered"
  ) as "open" | "registered" | "paid" | "restricted" | "embargoed";
  const tone =
    key === "open"
      ? "text-label-human"
      : key === "restricted" || key === "embargoed"
        ? "text-warning"
        : "text-ink-muted";
  return (
    <span
      className={`label inline-flex items-center gap-1 rounded-control border border-hairline px-2 py-0.5 ${tone}`}
    >
      {t(key)}
    </span>
  );
}
