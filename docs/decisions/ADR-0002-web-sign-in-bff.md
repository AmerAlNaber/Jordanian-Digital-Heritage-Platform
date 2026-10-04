# ADR-0002: Web sign-in through a backend-for-frontend with server-side sessions

Status: accepted (2026-10-04)

## Context

`SPEC.md` requires OIDC Authorization Code with PKCE through Keycloak (SEC-1), 10-minute access tokens with 8-hour member and 1-hour staff refresh tokens (SEC-2), session listing and revocation within 60 seconds (SEC-5), and a strict Content Security Policy with nonces (SEC-16). It does not say where the tokens live in the web application. Two designs satisfy the flow:

1. The browser holds the tokens (a public OIDC client with PKCE, tokens in memory or storage) and calls the API directly.
2. The Next.js server holds the tokens (a confidential client with PKCE), keeps them in a server-side session, and the browser carries only an opaque session cookie. Server components call the API with the session's access token.

## Decision

Option 2. `apps/web` is a backend-for-frontend:

- `/api/auth/login` starts the code flow with PKCE and a signed state cookie; `/api/auth/callback` (members, client `jdhp-web`) and `/api/auth/callback/staff` (staff, client `jdhp-staff`) exchange the code server-side with the client secret.
- Tokens are stored in Redis, encrypted with AES-256-GCM under a key derived from `SESSION_SECRET`; the browser receives an HMAC-signed, `HttpOnly`, `Secure`, `SameSite=Lax` cookie that names the session and nothing else.
- The session's lifetime follows the Keycloak client: 8 hours for members, 1 hour for staff (SEC-2). Refresh happens server-side; a failed refresh ends the session.
- `/api/auth/logout` destroys the session and sends the browser to Keycloak's end-session endpoint.
- Every page is rendered per request (`dynamic = "force-dynamic"`), so the CSP nonce, the signed-in state and the catalog's access decisions are never baked into a build (SEC-16).
- Startup validates the configuration (`instrumentation.ts`); the process refuses to serve with a missing variable (SEC-19).

## Consequences

- No token is ever readable by page scripts, so a cross-site scripting bug cannot exfiltrate one; the CSP stays an added layer rather than the only one (SEC-13, SEC-16).
- Revoking a session is a Redis delete, which makes the 60-second propagation target for SEC-5 a matter of the grant cache in the API, not of token expiry in browsers.
- The web application needs Redis and the two client secrets; it cannot be served as a static export. This matches the Compose and k3s shapes already required by the stack.
- Server components fetch the API over the internal network with `Accept-Language` and the user's token; anonymous reads may be cached for 60 seconds, signed-in reads never are.
- The reader (Phase 1) will obtain short-lived tile tokens from the API through the same session; it never sees the OIDC tokens either (SEC-10).
