# Testing rig

A public copy of the whole stack on one server, reachable from anywhere, holding only the
fictional seed library. It exists so people can test the platform before any real material or
real user is involved. It is not the pilot: no backups, no secret store, a shared test inbox,
and the identity provider's console on the public hostname behind one password (ADR-0010).

## What you need

| Item | Minimum | Notes |
| --- | --- | --- |
| Server | Ubuntu 24.04, 4 vCPU, 16 GB RAM, 80 GB SSD | OpenSearch, PostgreSQL, Keycloak, the image server and the apps run side by side; 8 GB works for one or two testers but swaps under load |
| Network | Ports 22, 80 and 443 open | Caddy obtains the certificate itself; nothing else is published |
| Hostname | A DNS name pointing at the server | Without a domain, `203-0-113-10.sslip.io` style names resolve to the embedded address and work with automatic TLS |
| Repository access | Read access to this repository from the server | A public repository needs nothing; a private one needs a deploy key or a read-only token in the clone URL |

Any provider that gives a plain Ubuntu machine with a public address will do (Hetzner, DigitalOcean, Linode, AWS Lightsail, or a machine in the institution's own rack).

## Bring it up

On the server, as root:

```sh
git clone --branch main https://github.com/AmerAlNaber/Jordanian-Digital-Heritage-Platform.git /opt/jdhp
sudo bash /opt/jdhp/deploy/testrig/bootstrap.sh --host heritage-test.example.org
```

The script installs Docker when it is missing, writes `.env` with generated secrets, sets the hostname and the testing-rig variables, builds the images, starts the stack, waits for the edge, ingests the seed library and creates the tester accounts. It takes ten to twenty minutes the first time, most of it image builds and the seed ingest. At the end it prints the addresses and where the credentials are. It never prints a credential.

To deploy a newer commit later:

```sh
sudo bash /opt/jdhp/deploy/testrig/bootstrap.sh --host heritage-test.example.org --skip-seed
```

To start over with empty data:

```sh
cd /opt/jdhp && COMPOSE_FILE=docker-compose.yml:infra/compose/compose.testrig.yaml docker compose down -v
sudo bash /opt/jdhp/deploy/testrig/bootstrap.sh --host heritage-test.example.org
```

## What testers get

- **The site** at `https://<host>/ar` and `https://<host>/en`, light and dark.
- **The test inbox** at `https://<host>/mail/`, behind the inbox user and password from
  `/opt/jdhp/.testrig-inbox-credentials`. Every verification email the identity provider sends
  lands here, and every SMS code too: the rig's SMS adapter emails each code to one address with
  the destination number in the subject. Testers register with any address, real or invented, and
  read the message here. Nothing leaves the server.
- **One account per role**, all with the password in `JDHP_TESTRIG_USER_PASSWORD` in `/opt/jdhp/.env`:
  `member@<host>`, `verified-researcher@<host>`, `curator@<host>`, `reviewer@<host>`,
  `rights-officer@<host>` and `platform-admin@<host>`. Staff accounts enrol a one-time code on
  first sign-in and then sign in again with it; the platform admin also enrols a hardware key.
  This is the real staff flow, not a shortcut.
- **The identity provider's console** at `https://<host>/auth/admin/`, behind the same inbox
  password, then `KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` from `.env`.
- **The seed library**: the 40-page chronicle of Sumayra and ten short fictional books that
  spread across ten governorates, five periods, seven material types and all five access
  classes. Two are open, three registered, two paid, two restricted and one embargoed, so the
  catalogue, the facets, the sample-page limits and the embargo rule can all be seen at once.
  The embargoed memoir is published yet invisible to the public: searching for Jerash as a
  visitor finds nothing; a staff account sees it.

## What to test

1. Browse and search in both languages, with and without diacritics; check that no page text is
   ever shown, selectable or copyable, only scans.
2. Register, verify the email from the inbox, choose a password, verify a phone with the code
   from the inbox, read the chronicle, print two pages.
3. Try a paid or restricted book as a member: the sample pages open, the rest refuses. Requests
   and payments arrive in Phase 2.
4. Sign in as the rights officer, enrol the code, sign in again with it, read the audit log,
   take a signed export.
5. Switch themes and languages midway, resize to a phone width, use a screen reader.

Report what you find as issues in the repository with the page address, the account used and
the time, so the audit log can be read alongside.

## Caveats

- The breached-password check calls the public range API from the server; when it is
  unreachable the rig accepts the password and logs a warning (fail-open default).
- Mailpit keeps the last five thousand messages in memory; the inbox is shared by every tester.
- Secrets live in `/opt/jdhp/.env` on the server, readable by root only. Rotate them by deleting
  the file and running the bootstrap again (that also empties the data).
- There is no backup. Anything worth keeping is in the repository, not on the rig.
