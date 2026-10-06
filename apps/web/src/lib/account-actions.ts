/**
 * Sign-in entry points and the Keycloak actions the account page may start (ACC-1, ACC-2).
 *
 * Registration and credential management stay in Keycloak; the web application only builds
 * the authorization request that opens the right screen (ADR-0002, ADR-0009).
 */

/** Application-initiated actions, by the name the account page uses. */
export const ACCOUNT_ACTIONS = {
  totp: "CONFIGURE_TOTP",
  passkey: "webauthn-register-passwordless",
  password: "UPDATE_PASSWORD",
  securityKey: "webauthn-register",
} as const;

export type AccountAction = keyof typeof ACCOUNT_ACTIONS;

export function isAccountAction(value: string | null): value is AccountAction {
  return value !== null && Object.hasOwn(ACCOUNT_ACTIONS, value);
}

/** The Keycloak `kc_action` value for an allowed action, or null for anything else. */
export function keycloakAction(value: string | null): string | null {
  return isAccountAction(value) ? ACCOUNT_ACTIONS[value] : null;
}

/** The locale Keycloak should render in, taken from the path the user returns to. */
export function uiLocale(returnTo: string): "ar" | "en" {
  return returnTo.startsWith("/en/") || returnTo === "/en" ? "en" : "ar";
}

/** The BFF sign-in URL that returns to `returnTo`, optionally registering or starting an action. */
export function loginHref(options: {
  returnTo: string;
  register?: boolean;
  action?: AccountAction;
  staff?: boolean;
  /** Ask the provider to run the whole sign-in again, whatever session it holds (SEC-3). */
  reauth?: boolean;
}): string {
  const params = new URLSearchParams({ return: options.returnTo });
  if (options.register) params.set("register", "1");
  if (options.action) params.set("action", options.action);
  if (options.staff) params.set("staff", "1");
  if (options.reauth) params.set("reauth", "1");
  return `/api/auth/login?${params.toString()}`;
}
