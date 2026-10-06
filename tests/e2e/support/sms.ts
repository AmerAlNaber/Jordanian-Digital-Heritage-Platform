import { execFile } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

/**
 * The mock SMS adapter logs every message it would have sent. In the Compose stack that log is
 * the API container's; E2E_SMS_LOG_COMMAND overrides the command that prints it.
 */
export async function latestSmsCode(timeoutMs = 30_000): Promise<string> {
  const command =
    process.env.E2E_SMS_LOG_COMMAND ?? "docker compose logs --no-color --tail 300 api";
  const [program, ...args] = command.split(" ");
  if (!program) throw new Error("empty E2E_SMS_LOG_COMMAND");
  const started = Date.now();
  let seen = "";
  while (Date.now() - started < timeoutMs) {
    const { stdout, stderr } = await run(program, args, { maxBuffer: 16 * 1024 * 1024 });
    seen = `${stdout}\n${stderr}`;
    const lines = seen.split("\n").filter((l) => l.includes("sms_mock_sent"));
    const last = lines.at(-1);
    const code = last?.match(/\b(\d{6})\b/)?.[1];
    if (code) return code;
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error(`no sms_mock_sent line with a code in the API log:\n${seen.slice(-800)}`);
}
