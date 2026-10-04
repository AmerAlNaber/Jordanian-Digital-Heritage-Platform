# CLAUDE.md

This repository is the core layer of the Jordanian Digital Heritage Platform: a secure digital library for a protected heritage collection. The full specification is `SPEC.md`. Read it in full at the start of every session. Every requirement in it is binding unless an ADR in `docs/decisions/` supersedes it.

## First session

Before writing any code:

1. Confirm the open decisions in the last section of `SPEC.md` with me and record the answers as `docs/decisions/ADR-0001-stack.md`.
2. Produce `docs/ARCHITECTURE.md` and `docs/THREAT_MODEL.md` from the spec.
3. Scaffold the monorepo exactly as the repository structure section describes.
4. Implement in the phase order given. Do not start a later phase before the acceptance criteria of the current one pass in CI.

## Rules that never bend

- Protected content never leaves the server as a downloadable original. Pages are served as watermarked tiles through the authorizing image server only. If a feature seems to need the original, stop and ask.
- OCR text is internal. It feeds search, indexing, and translation. It is never rendered, selectable, or copyable in any user interface. The scan is the page.
- Every object with origin `ai` is created at `pending` and is invisible outside the review portal until a Reviewer approves it. No code path sets `approved` except the portal action.
- Every API route calls the policy engine. The route-coverage test must pass with zero unprotected routes before any merge.
- Never commit secrets. Configuration comes from environment variables validated at startup. `.env.example` documents every variable with no real values.
- Arabic is first-class from the first commit. Every string externalized, CSS logical properties only, `dir` on every content container.
- Every endpoint, model, and migration ships with tests. Coverage gate is 80 percent on `apps/api`.
- For every security requirement (SEC-n) write the test that proves it before the feature.
- Ask before deviating from any named standard, library, or security control in `SPEC.md`.

## Working conventions

- Conventional Commits. Squash merges. Protected `main`.
- Every pull request updates `CHANGELOG.md`. Where a design choice was made, add a one-page ADR to `docs/decisions/`.
- Python: ruff, mypy strict, Pydantic at every boundary. TypeScript: strict, no `any`, Prettier.
- Reference requirement IDs (CAT-4, SEC-10, TRN-1, and so on) in commit messages and test names so work traces back to the spec.
- Seed data is the fictional 40-page book in the repo. No real heritage material ever enters a test fixture.
- When unsure which of two approaches the spec intends, propose both in one message with a recommendation and wait.

## Stack summary

Next.js 15 web, FastAPI API, Celery workers, Keycloak, Cerbos, PostgreSQL 16 with pgvector, OpenSearch with Arabic analyzer, Redis, S3-compatible object storage, Cantaloupe IIIF image server, Caddy behind Cloudflare. OCR, language models, embeddings, payments, and messaging all sit behind adapter interfaces in `packages/ai-adapters` and `apps/api`. Docker Compose for local and pilot, k3s manifests for production. Details and justification are in `SPEC.md`.
