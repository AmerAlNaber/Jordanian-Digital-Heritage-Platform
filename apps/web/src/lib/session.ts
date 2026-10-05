// Backend-for-frontend session store (SEC-1, SEC-2). The browser holds one httpOnly cookie with a
// signed session id; tokens live in Redis, encrypted with a key derived from SESSION_SECRET.
import {
  createCipheriv,
  createDecipheriv,
  createHmac,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";

import Redis from "ioredis";
import { cookies } from "next/headers";

import { env, isProduction } from "./env";

export const SESSION_COOKIE = "jdhp_session";
const MEMBER_TTL_SECONDS = 8 * 3600;
const STAFF_TTL_SECONDS = 3600;

export type SessionData = {
  client: "web" | "staff";
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  expiresAt: number;
  subject: string;
  roles: string[];
  name?: string;
  createdAt: number;
};

let redis: Redis | undefined;
function store(): Redis {
  redis ??= new Redis(env("REDIS_URL"), {
    lazyConnect: false,
    maxRetriesPerRequest: 2,
    keyPrefix: "jdhp:web:",
  });
  return redis;
}

function key(): Buffer {
  return scryptSync(env("SESSION_SECRET"), "jdhp-web-session", 32);
}

function sign(id: string): string {
  return createHmac("sha256", env("SESSION_SECRET")).update(id).digest("base64url");
}

export function encodeCookie(id: string): string {
  return `${id}.${sign(id)}`;
}

export function decodeCookie(value: string | undefined): string | null {
  if (!value) return null;
  const [id, signature] = value.split(".");
  if (!id || !signature) return null;
  const expected = sign(id);
  if (expected.length !== signature.length) return null;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(signature)) ? id : null;
}

export function encrypt(plain: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), iv, { authTagLength: 16 });
  const body = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]).toString("base64url");
}

export function decrypt(payload: string): string {
  const raw = Buffer.from(payload, "base64url");
  const iv = raw.subarray(0, 12);
  const tag = raw.subarray(12, 28);
  const body = raw.subarray(28);
  const decipher = createDecipheriv("aes-256-gcm", key(), iv, { authTagLength: 16 });
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
}

export function ttlFor(client: SessionData["client"]): number {
  return client === "staff" ? STAFF_TTL_SECONDS : MEMBER_TTL_SECONDS;
}

export async function createSession(data: SessionData): Promise<string> {
  const id = randomBytes(32).toString("hex");
  await store().set(`sess:${id}`, encrypt(JSON.stringify(data)), "EX", ttlFor(data.client));
  return id;
}

export async function readSession(id: string): Promise<SessionData | null> {
  const payload = await store().get(`sess:${id}`);
  if (!payload) return null;
  try {
    return JSON.parse(decrypt(payload)) as SessionData;
  } catch {
    await store().del(`sess:${id}`);
    return null;
  }
}

export async function updateSession(id: string, data: SessionData): Promise<void> {
  const ttl = await store().ttl(`sess:${id}`);
  await store().set(
    `sess:${id}`,
    encrypt(JSON.stringify(data)),
    "EX",
    ttl > 0 ? ttl : ttlFor(data.client),
  );
}

export async function destroySession(id: string): Promise<void> {
  await store().del(`sess:${id}`);
}

export function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}

/** The current request's session, or null. Server components and route handlers only. */
export async function currentSession(): Promise<{ id: string; data: SessionData } | null> {
  const jar = await cookies();
  const id = decodeCookie(jar.get(SESSION_COOKIE)?.value);
  if (!id) return null;
  const data = await readSession(id);
  return data ? { id, data } : null;
}
