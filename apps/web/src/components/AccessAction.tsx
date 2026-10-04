import { useTranslations } from "next-intl";

import { accessState } from "@/lib/format";

export function AccessAction({
  locale,
  name,
  signedIn,
  canRead,
  canRequest,
}: {
  locale: string;
  name: string;
  signedIn: boolean;
  canRead: boolean;
  canRequest: boolean;
}) {
  const t = useTranslations("access");
  const state = accessState({ signedIn, canRead, canRequest });
  if (state === "anonymous") {
    return (
      <a
        href={`/api/auth/login?return=/${locale}/works/${name}`}
        className="control control-primary inline-flex w-fit items-center"
      >
        {t("signInToRead")}
      </a>
    );
  }
  if (state === "can_read") {
    // The secure reader is Phase 1; the action is present and labelled, not yet enabled.
    return (
      <button
        type="button"
        className="control control-primary w-fit"
        aria-disabled="true"
        title={t("readerSoon")}
      >
        {t("read")}
      </button>
    );
  }
  if (state === "can_request") {
    return (
      <button type="button" className="control w-fit" aria-disabled="true" title={t("readerSoon")}>
        {t("request")}
      </button>
    );
  }
  return <p className="label">{t("noAccess")}</p>;
}
