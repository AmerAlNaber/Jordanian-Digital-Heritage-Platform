# Keycloak realm

`realm-jdhp.template.json` is the realm of record. It is rendered with `envsubst` at container
start (see `infra/compose/keycloak/entrypoint.sh`) so that URLs and client secrets come from the
environment or the secret store, never from git (SEC-19).

What the realm encodes:

| Requirement | Setting |
| --- | --- |
| SEC-1 | Authorization Code only, PKCE S256 required on both web clients, no implicit or password grants |
| SEC-2 | Access tokens 600 s; refresh (SSO idle) 8 h for members; the `jdhp-staff` client caps staff sessions at 1 h; refresh rotation with `revokeRefreshToken` and zero reuse |
| SEC-3 | Browser flow `jdhp browser`: every `staff` role must present OTP; `platform_admin` must also present a WebAuthn hardware key; members who enrolled OTP must use it |
| SEC-4 | Brute-force protection: 10 failures, exponential wait up to 15 min |
| ACC-1 | Password policy: length over complexity (12+), history, not username or email |
| INT-1 | Arabic default locale, English second |

Open items tracked for Phase 1: the breached-password check (SEC-4) needs a password policy
provider that calls a k-anonymity API; SMS OTP for members needs the SMS adapter; the `jdhp`
login theme lives in `theme/` and is built with the design tokens.

Local development users are created by `infra/compose/keycloak/local-users.sh` with passwords
from `.env`. They do not exist in staging, pilot or production.
