# ADR-0010: Testing rig: a public single-server stack with a shared test inbox

Status: accepted. Date: 2026-10-06. Requirements: SEC-1, SEC-3, SEC-19, ADR-0001 D15.

## Context

Phase 1 is complete and CI proves the stack end to end, but the people who will use the
platform have only seen it through a reviewer's screen. They asked for a copy they can reach
from anywhere to start testing, with a richer catalogue than one book: several categories,
places, periods and every access class, restricted and embargoed titles included.

The pilot overlay (`compose.pilot.yaml`) assumes a secret store, a private network and real
content. None of that exists yet, and real content would be the wrong thing to test with.

## Decision

1. **A `testrig` environment that is public but not "deployed".** The API's settings gain
   `Environment.TESTRIG`: reachable from the internet, held to the local rules inside
   (plain HTTP between containers, mock providers allowed) and refused everything that only
   belongs where real content lives. It is a fourth kind of stack beside local, pilot and
   production, not a relaxed pilot.
2. **One Compose overlay, one Caddyfile.** `infra/compose/compose.testrig.yaml` publishes only
   ports 80 and 443; Caddy obtains the certificate for the hostname. The routes every stack
   shares moved to `routes.caddy`, so the rig's Caddyfile adds its two extras around the same
   site instead of copying it.
3. **The mail catcher is the shared test inbox.** Mailpit stays the SMTP target, as in CI, and
   its web inbox is served under `/mail/` behind one basic-auth credential. Testers register with
   any address and read the verification email there. The identity provider's console and master
   realm sit behind the same credential; the realm's own admin password is the second lock.
4. **SMS over email, as a testing adapter only.** `sms_provider = email` delivers each code as
   an email to one inbox address with the destination number in the subject. The settings refuse
   it wherever `holds_real_content` is true and demand an SMTP host for it. The phone code
   therefore reaches the same inbox as the verification email, and nothing leaves the server.
   The real gateway adapter stays a Phase 2 item (ADR-0009).
5. **One account per role, created by a profile service.** `testrig-users` runs once from the
   Keycloak image and creates a member, a verified researcher and the four staff roles with one
   password. Staff still enrol their second factor on first sign-in and sign in again with it,
   exactly as the suite does (ADR-0009 §7); the rig does not weaken SEC-3.
6. **A bootstrap script instead of a manual runbook.** `deploy/testrig/bootstrap.sh` takes a
   hostname, installs Docker, writes `.env` with generated secrets, sets the rig variables,
   builds, starts, seeds and creates the accounts. It writes the inbox credentials to a
   root-only file and never prints a secret. Re-running it updates the checkout and restarts.
7. **The seed library.** Ten short fictional books join the 40-page chronicle, written for the
   platform like the first one (ADR-0001 D15): governorate names are real catalogue subjects,
   every town, site, person and event is invented and says so. They cover open, registered,
   paid, restricted and embargoed classes, five periods, seven material types and three
   collections. CI ingests all eleven and now proves two things it could not before: public
   listings carry four classes and never the embargoed title, and a public search for the one
   word only the embargoed book uses returns nothing.

## Consequences

- The rig is a convenience with known limits: no backups, in-memory inbox, one shared inbox
  password, fail-open breached-password check. `docs/operations/testing-rig.md` states them.
- The seed ingest renders about 112 pages at 400 ppi; `make up` and the CI Compose job take a
  few minutes longer. `JDHP_SEED_SCALE` still shrinks the masters for a quick demo.
- Tests that locate the seed book search for its town name, which no other book uses; a new
  book must keep that true (there is a test for it).
- When real content arrives, nothing from this overlay is reused: the pilot overlay and the
  secret store are the path, and `testrig` refuses real providers' absence the way `local` does.
