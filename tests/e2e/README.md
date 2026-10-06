# End-to-end suite

Playwright against a running stack, in Arabic and English, light and dark, with axe on every page
it visits (ACX-1). It is the Phase 1 acceptance path: register in Arabic, verify the email, choose
a password, verify a phone, find the seed book by a word from its scanned text, read it, print two
pages, and find every one of those actions in the audit viewer as a rights officer who had to
enrol a one-time code first.

```sh
pnpm --filter @jdhp/e2e exec playwright install --with-deps chromium
E2E_KC_ADMIN_USER=... E2E_KC_ADMIN_PASSWORD=... pnpm --filter @jdhp/e2e e2e
```

| Variable | Default | Use |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://localhost:8080` | The stack's edge |
| `E2E_MAILPIT_URL` | `http://localhost:8025` | Mailpit's API, where verification emails land |
| `E2E_KC_ADMIN_USER`, `E2E_KC_ADMIN_PASSWORD` | | Keycloak administration, to create the officer and look up subjects |
| `E2E_SMS_LOG_COMMAND` | `docker compose logs --no-color --tail 300 api` | Prints the API log the mock SMS adapter writes codes to |
| `PLAYWRIGHT_CHROMIUM_PATH` | | A preinstalled Chromium instead of the downloaded one |

The package's `test` script is a no-op so the workspace-wide `pnpm test` stays stack-free; the suite runs as `e2e`. CI runs it in the Compose job after the seed ingest, with `infra/compose/compose.ci.yaml` publishing
Mailpit's API on the runner. Reports and traces of failures are uploaded as artifacts.
