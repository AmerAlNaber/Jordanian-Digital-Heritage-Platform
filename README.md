# Jordanian Digital Heritage Platform

A secure digital library for a protected Jordanian heritage collection. Catalog metadata is open to everyone and to every crawler; the scanned pages of protected works are read only inside the platform, as watermarked tiles served through an authorizing image server, never as downloadable originals. Arabic is the first language of the interface and of the content.

The full specification is [`SPEC.md`](SPEC.md). Every requirement in it is binding unless an architecture decision record in [`docs/decisions/`](docs/decisions/) supersedes it. Working rules for contributors and for Claude Code are in [`CLAUDE.md`](CLAUDE.md).

## Status

Phase 0, Foundation, is implemented: the monorepo, the Compose stack, the CI pipeline, the Keycloak realm, the Cerbos policies, the database schema with row-level security and the hash-chained audit trail, the design tokens, the intake pipeline, and the fictional 40-page seed book ingested through it with the mock OCR adapter. The reader, the review portal and everything that touches personal data follow in later phases in the order `SPEC.md` gives.

## Repository layout

```text
apps/web            Next.js 15 web application and sign-in BFF (TypeScript)
apps/api            FastAPI application: catalog, identity, intake, content, review, audit
apps/worker         Celery tasks: ingest, derivatives, OCR, embeddings, fixity
packages/schemas    the exported OpenAPI document and the TypeScript types generated from it
packages/design-tokens  tokens as JSON, built to CSS variables and a Tailwind preset
packages/metadata   METS, ALTO and checksum manifest builders and validators
packages/ai-adapters OCR, language model and embedding adapter interfaces and mock implementations
policies            Cerbos policies, resource schemas and their test suites
infra               Compose overrides, Keycloak realm, Cantaloupe, OpenSearch templates, k3s skeleton
docs                architecture, threat model, design, compliance matrix, decisions, runbooks
tests               end-to-end, load and search-relevance suites
```

## Quick start

Requirements: Docker with Compose v2, [uv](https://docs.astral.sh/uv/), Node 22 with [pnpm](https://pnpm.io) (`corepack enable`).

```sh
make setup                   # Python and Node dependencies
infra/compose/make-env.sh    # .env from .env.example with generated secrets
make up                      # build, start every service, ingest the seed book
```

Open <http://localhost:8080/ar> (or `/en`). The API answers under `/api`, Keycloak under `/auth`, outgoing mail is shown by Mailpit on <http://localhost:8025>. The runbook [`docs/operations/local-stack.md`](docs/operations/local-stack.md) explains what the stack does and how to check it.

## Development

```sh
make lint          # ruff, import-linter, bandit, ESLint, Prettier
make typecheck     # mypy strict, tsc
make test          # API with the 80 percent coverage gate, worker, Cerbos policies, web
make openapi       # export the OpenAPI document and regenerate packages/schemas
make migrate       # Alembic upgrade head against the running stack
make tokens        # rebuild the design tokens
```

The Python tests need a local PostgreSQL 16 with pgvector reachable as `JDHP_TEST_ADMIN_DATABASE_URL` (default `postgresql://postgres@localhost:54329/postgres`), a `cerbos` binary (`CERBOS_BIN`) or `JDHP_CERBOS_URL`, and `redis-server` on the path or `JDHP_TEST_REDIS_URL`. Every test runs against a database cloned from a migrated template, connecting as the restricted application role so row-level security is exercised, not bypassed.

## Rules that never bend

- Protected content never leaves the server as a downloadable original.
- OCR text is internal. It feeds search, indexing and translation; it is never rendered, selectable or copyable.
- Every object with origin `ai` is created at `pending` and is invisible outside the review portal until a Reviewer approves it.
- Every API route calls the policy engine; the route-coverage test must pass with zero unprotected routes.
- No secrets in the repository; configuration comes from environment variables validated at startup.
- Arabic is first-class: every string externalized, CSS logical properties only, `dir` on every content container.

The threat model in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) maps each security requirement to the test that proves it.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the core layer, its boundaries and the pipelines.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md): assets, personas, threats and controls.
- [`docs/DESIGN.md`](docs/DESIGN.md): typefaces, scale, colour and the label system.
- [`docs/COMPLIANCE_MATRIX.md`](docs/COMPLIANCE_MATRIX.md): data categories, bases and retention (completed in Phase 3).
- [`docs/decisions/`](docs/decisions/): architecture decision records, starting with the stack.
- [`CHANGELOG.md`](CHANGELOG.md): every change, with the requirement identifiers it serves.

## Seed data

The only content in this repository is fictional and written for the platform: the 40-page book «أخبار بلدة سُمَيْرة» in `apps/api/src/jdhp_api/seed/book/` and ten short books in `apps/api/src/jdhp_api/seed/library/` that spread across ten governorates, several periods and material types and all five access classes (two open, three registered, two paid, two restricted, one embargoed). Their scans are rendered from text, so no real heritage material is ever in a test fixture or a demo. `docker compose run --rm seed` ingests all eleven; `--only seed-book` ingests the chronicle alone.

## Testing rig

A public copy of the stack for testers, on one server with automatic TLS, a shared test inbox for verification emails and SMS codes, and one account per role: [`docs/operations/testing-rig.md`](docs/operations/testing-rig.md) and `deploy/testrig/bootstrap.sh` (ADR-0010).
