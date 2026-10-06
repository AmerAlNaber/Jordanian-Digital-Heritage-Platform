/** Keycloak administration for test setup only: staff accounts and subject lookups. */

const BASE = (process.env.E2E_BASE_URL ?? "http://localhost:8080").replace(/\/$/, "");
const REALM = "jdhp";

async function adminToken(): Promise<string> {
  const user = process.env.E2E_KC_ADMIN_USER;
  const password = process.env.E2E_KC_ADMIN_PASSWORD;
  if (!user || !password)
    throw new Error("E2E_KC_ADMIN_USER and E2E_KC_ADMIN_PASSWORD are required");
  const response = await fetch(`${BASE}/auth/realms/master/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "password",
      client_id: "admin-cli",
      username: user,
      password,
    }),
  });
  if (!response.ok) throw new Error(`admin token: ${response.status} ${await response.text()}`);
  return ((await response.json()) as { access_token: string }).access_token;
}

async function admin(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await adminToken();
  return fetch(`${BASE}/auth/admin/realms/${REALM}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
}

export async function subjectOf(email: string): Promise<string> {
  const response = await admin(`/users?email=${encodeURIComponent(email)}&exact=true`);
  const users = (await response.json()) as { id: string }[];
  const [user] = users;
  if (!user) throw new Error(`no Keycloak user for ${email}`);
  return user.id;
}

/** A staff account with a password and no second factor yet: the sign-in flow makes them enrol one. */
export async function createStaffUser(
  email: string,
  password: string,
  role: string,
): Promise<string> {
  const created = await admin("/users", {
    method: "POST",
    body: JSON.stringify({
      username: email,
      email,
      enabled: true,
      emailVerified: true,
      firstName: "E2E",
      lastName: role,
      credentials: [{ type: "password", value: password, temporary: false }],
    }),
  });
  if (created.status !== 201)
    throw new Error(`create user: ${created.status} ${await created.text()}`);
  const id = await subjectOf(email);
  const roleResponse = await admin(`/roles/${role}`);
  const roleRep = (await roleResponse.json()) as { id: string; name: string };
  const mapped = await admin(`/users/${id}/role-mappings/realm`, {
    method: "POST",
    body: JSON.stringify([{ id: roleRep.id, name: roleRep.name }]),
  });
  if (!mapped.ok) throw new Error(`role mapping: ${mapped.status} ${await mapped.text()}`);
  return id;
}
