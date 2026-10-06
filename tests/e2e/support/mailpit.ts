/** Mailpit catches every email the stack sends; the tests read verification links from it. */

const MAILPIT = (process.env.E2E_MAILPIT_URL ?? "http://localhost:8025").replace(/\/$/, "");

type Summary = { ID: string; To: { Address: string }[]; Subject: string; Created: string };
type Message = { ID: string; HTML: string; Text: string; Subject: string };

async function search(to: string): Promise<Summary[]> {
  const response = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`);
  if (!response.ok) return [];
  const body = (await response.json()) as { messages?: Summary[] };
  return body.messages ?? [];
}

export async function waitForEmail(to: string, timeoutMs = 60_000): Promise<Message> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const [latest] = await search(to);
    if (latest) {
      const response = await fetch(`${MAILPIT}/api/v1/message/${latest.ID}`);
      if (response.ok) return (await response.json()) as Message;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error(`no email for ${to} within ${timeoutMs} ms`);
}

/** The first link in the message that points into the stack's identity provider. */
export function verificationLink(message: Message): string {
  const haystack = `${message.HTML}\n${message.Text}`;
  const links = [...haystack.matchAll(/https?:\/\/[^\s"'<>]+/g)].map((m) =>
    m[0].replace(/&amp;/g, "&"),
  );
  const link = links.find((l) => l.includes("/auth/realms/") && l.includes("login-actions"));
  if (!link) throw new Error(`no verification link in email ${message.ID}: ${links.join(", ")}`);
  return link;
}
