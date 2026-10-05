# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow Semantic Versioning once the first release is tagged. Entries reference requirement identifiers from `SPEC.md` where they apply.

## [Unreleased]

### Added

- `docs/decisions/ADR-0001-stack.md`: accepted record of the specified stack and the open decisions D1 to D17 (all defaults, repository name with `jdhp` as the technical short name, workers reuse the API package in-process).
- `docs/ARCHITECTURE.md`: architecture of the core layer derived from `SPEC.md`.
- `docs/THREAT_MODEL.md`: threat model derived from `SPEC.md`, covering SEC-1 to SEC-31, REV-1, RDR-1 and CAT-4 with the test that proves each control.
- `CHANGELOG.md`.
- API (`apps/api`): FastAPI modular monolith with configuration validated at startup (SEC-19), Keycloak token verification with the 10-minute lifetime enforced (SEC-1, SEC-2), the `Authorize` dependency that asks Cerbos on every route and fails closed (SEC-6, SEC-7), hash-chained append-only audit events (SEC-8), UUIDv7 keys and ARK identifiers (INT-7), catalog, identity, intake, content, review and audit routes, and the route-coverage test that fails on any unprotected route.
- Database: Alembic migrations for the Phase 0 schema with row-level security on every table that holds personal or access data, the review guard trigger that keeps AI objects `pending` until a Reviewer approves them in the portal (REV-1), and the audit trigger that forbids update and delete (SEC-8).
- Policies (`policies/`): Cerbos derived roles and resource policies for works, pages, content objects, review tasks, intake batches and audit, with 815 test cases covering every role and access class, including denials (SEC-6).
- Packages: `ai-adapters` with the OCR, language model and embedding interfaces and mock providers refused outside local and test (TRN-6); `metadata` with METS, ALTO and checksum builders behind hardened XML parsing.
- Seed: the fictional 40-page book, a renderer that produces 400 ppi masters with ground truth, and the pipeline that ingests it (ADM-1).
- Worker (`apps/worker`): Celery application and inline runner; intake validation, preservation write, METS and checksums, JP2/PTIF derivatives and marked samples (SEC-14), mock OCR to ALTO, page and work indexing (CAT-4), embeddings with model and version recorded (SRCH-6), fixity verification that freezes a work and opens an incident on mismatch (SEC-26).
- Infrastructure: Docker Compose stack for local and pilot with Caddy, Keycloak realm template and MFA flows (SEC-1 to SEC-4), Cerbos, PostgreSQL with pgvector, OpenSearch with the Arabic analyzer, Redis, MinIO with object lock, Cantaloupe behind an HMAC-authorizing delegate (SEC-10), Mailpit; `.env.example` documents every variable and `infra/compose/make-env.sh` generates local secrets; k3s skeleton under `infra/k8s`.
- Design (`packages/design-tokens`, `docs/DESIGN.md`): OKLCH tokens built to CSS variables and a Tailwind preset with contrast tests (ACX-4); typeface decision (INT-3).
- Web (`apps/web`, `packages/schemas`): Next.js 15 application with Arabic as the default locale, externalized strings (INT-1), logical properties and `dir` on every container (INT-2), locale numerals and Hijri dates (INT-4), per-request CSP nonces and security headers (SEC-16), `robots.txt` welcoming AI crawlers on open metadata (SEO-5), machine-readable citations and ARK resolution (SEO-7), and a BFF sign-in with PKCE and encrypted server-side sessions (SEC-1, SEC-2); catalog, collection, subject, record and account pages typed from the OpenAPI document.
- CI (`.github/workflows/ci.yml`): lint and type checks, API tests with the 80 percent coverage gate against real PostgreSQL, Redis and Cerbos, worker and policy tests, web tests and build, OpenAPI and generated-type sync checks, Semgrep, Bandit, pip-audit, npm audit, gitleaks, image builds scanned with Trivy (SEC-18, SEC-20), and the Compose integration job that brings up every service and ingests the seed book.
- `docs/COMPLIANCE_MATRIX.md` skeleton, `docs/operations/` runbooks, `tests/load` and `tests/search-eval` placeholders.

### Security

- Next.js pinned to 15.5.24 and transitive `postcss` and `sharp` raised through `pnpm.overrides` so `pnpm audit` passes at the high level (SEC-18). One advisory without a patched release, GHSA-vfj7-8cjw-p6xm in the development-only `braces` dependency of the Next.js ESLint plugin, is listed in `pnpm.auditConfig.ignoreGhsas` until a fix ships.
- Images apply the base distribution's security updates at build time, the web runtime image carries only Node.js (npm, corepack and yarn are removed with their bundled dependencies), and Trivy blocks any high or critical finding not accepted in `.trivyignore` with a written reason (SEC-18).
- MinIO withdrew its container images from the public registries, so the object store is built from the pinned MinIO and mc source releases in `infra/compose/minio` (ADR-0003), with the Go modules Trivy names raised to their fixed versions at build time; the image is scanned like every other.
- Cantaloupe moves to 5.0.7, the latest release. Its image is scanned for operating system packages only: the Java libraries bundled in the upstream release carry fixed vulnerabilities that cannot be replaced without rebuilding Cantaloupe from source. The Phase 1 tile gateway work decides between a source build with current dependencies and another IIIF server; until then the image is reachable only from the tile gateway on the internal network.
