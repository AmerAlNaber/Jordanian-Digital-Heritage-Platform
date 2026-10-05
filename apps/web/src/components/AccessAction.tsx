import { useTranslations } from "next-intl";

import { Link } from "@/i18n/routing";
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
  if (state === "can_read") {
    return (
      <Link
        href={`/read/${name}`}
        className="control control-primary inline-flex w-fit items-center no-underline"
      >
        {t("read")}
      </Link>
    );
  }
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
  if (state === "can_request") {
    // Access requests arrive with Phase 2; the action is present and labelled, not yet enabled.
    return (
      <button type="button" className="control w-fit" aria-disabled="true" title={t("requestSoon")}>
        {t("request")}
      </button>
    );
  }
  return <p className="label">{t("noAccess")}</p>;
}
