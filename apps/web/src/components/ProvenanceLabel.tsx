import type { ContentObjectOut } from "@jdhp/schemas";

/** The label system (SRC-1, SRC-2): what the content is and who or what produced it. */
export function ProvenanceLabel({ object, locale }: { object: ContentObjectOut; locale: string }) {
  const text = locale === "ar" ? object.label_ar : object.label_en;
  const tone = object.origin === "ai" ? "label-ai" : "label-human";
  const reviewed = object.reviewed_at ? new Date(object.reviewed_at) : null;
  const date = reviewed
    ? new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", { dateStyle: "long" }).format(
        reviewed,
      )
    : null;
  return (
    <p className={`label ${tone}`} dir={locale === "ar" ? "rtl" : "ltr"} lang={locale}>
      {text}
      {date ? <time dateTime={object.reviewed_at ?? undefined}> · {date}</time> : null}
    </p>
  );
}
