# ADR-0009: Account security: breached-password check, passkeys, phone verification and sessions

Status: accepted. Date: 2026-10-05. Requirements: ACC-1, ACC-2, SEC-3, SEC-4, SEC-5.

## Context

Phase 0 encoded the realm of record: Authorization Code with PKCE, token lifetimes, mandatory
one-time codes for staff, hardware keys for platform admins, brute-force lockout and a password
policy that prefers length over complexity (ADR-0001, `infra/keycloak/README.md`). Phase 1 asks
for registration a member can complete in Arabic, with email and phone verification, a
breached-password check against a k-anonymity API, optional passkeys, and a session list the
member can act on. Keycloak carries none of the breached-password check, the phone step or an
SMS second factor out of the box.

## Decision

1. **Breached-password check as a Keycloak password-policy provider.** `infra/keycloak/extensions`
   is a small Maven project that adds the policy `breachedPassword(n)`: the password's SHA-1 is
   computed, its first five hex characters are sent to a Pwned Passwords style range API with
   padding requested, and the match is made locally; more than `n` sightings refuses the
   password, at registration, reset and change alike, because Keycloak evaluates password
   policies in every path that sets a password. The realm sets `breachedPassword(0)`.
   The range API endpoint is `JDHP_PWNED_RANGE_URL` (default the public Have I Been Pwned range
   API); when it cannot be reached the check **fails open** and logs a warning, unless
   `JDHP_BREACHED_PASSWORD_FAIL_CLOSED=true`. An outage of a third party must not stop
   registration on a platform whose other controls (length policy, lockout, MFA) still hold;
   deployments that prefer refusal switch the variable. Neither the password nor the user is
   logged. The provider is unit-tested against a local stub of the range API.

2. **Keycloak is built from a repository Dockerfile and pinned.** `infra/keycloak/Dockerfile`
   compiles and tests the extensions, copies the jar and the `jdhp` login theme into the upstream
   image `quay.io/keycloak/keycloak:26.7.5` and runs an optimized build. The version is pinned in
   both the Dockerfile and `pom.xml` and the image joins the CI build-and-scan matrix. The
   alternative, a third-party extension image, would move a security control outside review.

3. **Passkeys for members; a one-time code for every staff role.** The browser flow asks for
   the username first, then a credential in a *required* sub-flow: a passkey (resident,
   user-verified WebAuthn credential on any authenticator) or a password. Only after that do the
   conditional sub-flows run: whoever enrolled a one-time code presents it; staff who have not
   presented a code in this sign-in must present one, enrolling first if they have none; platform
   admins must present a hardware key as well (SEC-3). The credential step sits outside every
   condition on purpose: a condition that cannot evaluate disables its sub-flow, and the first
   draft of this change, which put the credentials inside role-conditional sub-flows, signed a
   member in on the username alone when the role condition silently failed. Each credential step
   carries an authentication-method reference (`pwd`, `swk`, `otp`, `hwk`), so the `amr` claim
   tells the API what was presented and `mfa` is decided from it. Members enrol a passkey, an
   authenticator app or a new password through Keycloak's own screens, started from the account
   page as application-initiated actions (`kc_action`); registration opens with `prompt=create`,
   asks for name and email, and lets the member choose the password after the address is verified,
   which is this Keycloak version's default and means no credential exists for an unverified
   address. The web application never handles a credential (ADR-0002).

4. **Phone verification on the platform, after the first sign-in.** Keycloak verifies the email
   address; the platform asks for the phone number on the account page, sends a one-time code
   through the SMS adapter and records the verified number on the user. The member's
   verification level becomes `phone` only then, which is what the Member role in `SPEC.md`
   requires. This keeps the SMS adapter in one place and needs no Keycloak extension; an SMS
   second factor at sign-in (allowed for members, SEC-3) is a later extension and is not needed
   for ACC-2 because authenticator apps and passkeys are available to every member.

5. **Sessions.** Member tokens carry the `account` audience so the member's own token can list and
   end their Keycloak sessions through the Account REST API; the platform ends the reader
   sessions that belong to a revoked sign-in session, which is what makes revocation reach an
   open reader within the cache window (SEC-5). Staff revocation of another user's sign-in
   sessions needs Keycloak administration credentials in the API and arrives with the rights
   screens in Phase 2.

6. **The realm is verified against the real server before it ships.** Importing the template
   into Keycloak 26.7.5 and driving registration, sign-in and password change through its forms
   found five defects the data-only realm tests had passed: the role condition read a key this
   version does not know (`condUserRole`), so staff MFA never applied; the `staff` composite
   pointed the wrong way (a composite grants its children, so a curator never held `staff`);
   listing one client scope suppressed Keycloak's built-in `profile`, `email`, `roles` and `basic`
   scopes, so a browser sign-in failed with `invalid_scope` and tokens carried no roles; the default
   role's composites were not imported from the `defaultRole` block; and the realm's frontend URL
   lacked the `/auth` path every rendered link needs. All five are fixed in the template and each
   has a realm test; the end-to-end check is `scratchpad`-only tooling for now and becomes part of
   the Playwright suite in Phase 1.

## Consequences

- The Keycloak image build needs Maven Central and the Keycloak image registry at build time,
  as the other images need their registries.
- Registration depends on the range API being reachable from the Keycloak container, or on the
  fail-open default; both are stated in `.env.example`.
- The realm tests read the template as data and prove the flow shape; the Compose job imports
  the realm into the real server on every run.
