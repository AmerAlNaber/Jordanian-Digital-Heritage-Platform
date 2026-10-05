# Keycloak

`realm-jdhp.template.json` is the realm of record. It is rendered with the environment by
`infra/compose/keycloak/render-realm.py` at container start so that URLs and client secrets come
from the environment or the secret store, never from git (SEC-19).

`Dockerfile` builds the server image: the extensions in `extensions/` (Maven, unit-tested in the
build) and the `jdhp` login theme in `theme/` go into the pinned upstream image. The Keycloak
version is pinned in the Dockerfile and in `extensions/pom.xml` together.

What the realm encodes:

| Requirement | Setting |
| --- | --- |
| SEC-1 | Authorization Code only, PKCE S256 required on both web clients, no implicit or password grants |
| SEC-2 | Access tokens 600 s; refresh (SSO idle) 8 h for members; the `jdhp-staff` client caps staff sessions at 1 h; refresh rotation with `revokeRefreshToken` and zero reuse |
| SEC-3 | Browser flow `jdhp browser`: username first, then a passkey or a password in a required sub-flow, then the second factors: anyone who enrolled a code presents it, staff who have not yet presented a code enrol or enter one, `platform_admin` presents a hardware key as well. Every step carries an `amr` reference |
| SEC-4 | Brute-force protection: 10 failures, exponential wait up to 15 min; `breachedPassword(0)` refuses any password seen in a breach (extension, ADR-0009) |
| ACC-1 | Registration with email verification; password policy: length over complexity (12+), history, not username or email, breach check; passkeys for members (resident, user-verified) |
| ACC-2 | Members enrol an authenticator app or a passkey from the account page (`kc_action`); members who enrolled a code must use it |
| SEC-5 | Tokens carry the `account` audience so a member's own token can list and end their sessions |
| INT-1 | Arabic default locale, English second |

Two shapes matter when editing the realm: a composite grants its children, so each staff role
includes `staff` rather than the reverse; and a realm that lists any client scope gets none of
Keycloak's built-in scopes, so `basic`, `profile`, `email`, `roles`, `web-origins`, `acr` and `phone`
are listed in full. Role conditions use this version's `condUserRole` key. The realm tests in
`apps/api/tests/infra/test_keycloak_realm.py` hold each of these.

Extension settings: `JDHP_PWNED_RANGE_URL` (default the public Have I Been Pwned range API) and
`JDHP_BREACHED_PASSWORD_FAIL_CLOSED` (default `false`: an unreachable range API logs a warning and
lets the password through). Still open: an SMS one-time code at sign-in for members (SEC-3), which
needs an authenticator extension and the SMS adapter.

Local development users are created by `infra/compose/keycloak/local-users.sh` with passwords
from `.env`. They do not exist in staging, pilot or production.
