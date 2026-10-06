import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Lang } from "./fixtures";

export type MemberState = { email: string; password: string; subject?: string; work?: string };

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", ".state");

/** The member one spec registers is the one the staff spec looks for in the audit log. */
export function saveMember(lang: Lang, state: MemberState): void {
  mkdirSync(root, { recursive: true });
  writeFileSync(join(root, `member-${lang}.json`), JSON.stringify(state, null, 2));
}

export function loadMember(lang: Lang): MemberState {
  try {
    return JSON.parse(readFileSync(join(root, `member-${lang}.json`), "utf8")) as MemberState;
  } catch {
    return { email: "", password: "" };
  }
}
