import { getTranslations } from "next-intl/server";

import type { Schemas } from "@jdhp/schemas";

type AuditEventOut = Schemas["AuditEventOut"];

function when(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

/** Audit events as a table: who did what to which resource, when, and how it ended (ADM-5). */
export async function AuditTable({ events, locale }: { events: AuditEventOut[]; locale: string }) {
  const t = await getTranslations("audit");
  if (events.length === 0) return <p className="mt-6 text-ink-muted">{t("none")}</p>;
  return (
    // The wide table scrolls sideways; a keyboard reaches the region through the focus stop.
    <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label={t("title")}>
      <table className="w-full border-collapse text-step-n1">
        <thead>
          <tr className="hairline-bottom text-start">
            {(
              [
                "seq",
                "when",
                "actor",
                "action",
                "resource",
                "outcome",
                "severity",
                "details",
              ] as const
            ).map((column) => (
              <th key={column} scope="col" className="label px-2 py-2 text-start font-normal">
                {t(`columns.${column}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.seq} className="hairline-bottom align-top">
              <td className="px-2 py-2 font-mono" dir="ltr">
                {event.seq}
              </td>
              <td className="px-2 py-2 whitespace-nowrap" dir="ltr">
                {when(event.occurred_at, locale)}
              </td>
              <td className="px-2 py-2 font-mono" dir="ltr">
                {event.actor_id}
                <span className="block text-ink-muted">{event.actor_roles.join(", ")}</span>
              </td>
              <td className="px-2 py-2 font-mono" dir="ltr">
                {event.action}
              </td>
              <td className="px-2 py-2 font-mono" dir="ltr">
                {event.resource_kind}/{event.resource_id}
              </td>
              <td className="px-2 py-2">{t(`outcomes.${event.outcome}`)}</td>
              <td className="px-2 py-2">{t(`severities.${event.severity}`)}</td>
              <td className="px-2 py-2 font-mono text-ink-muted" dir="ltr">
                {Object.keys(event.details).length > 0 ? JSON.stringify(event.details) : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
