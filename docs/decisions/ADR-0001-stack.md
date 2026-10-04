# ADR-0001: Stack confirmation and open decisions for the core layer

| | |
| --- | --- |
| Status | **Accepted** on 2026-10-04. The owner confirmed every specification default, chose the repository name for D1 and option B for D17. |
| Date | 2026-10-04 |
| Deciders | Amer Al-Naber (owner) |
| Proposer | Claude Code, first session |
| Supersedes | None |
| Related | `SPEC.md` sections "Architecture and technology stack" and "Open decisions to confirm before the first session"; `docs/ARCHITECTURE.md`; `docs/THREAT_MODEL.md` |

## Context

`SPEC.md` fixes the technology stack for the core layer and lists sixteen open decisions, each with a default. `CLAUDE.md` requires that these decisions are confirmed with the owner before any code is written and that the answers are recorded here. The architecture and threat model drafted in the same session follow the decisions below; every passage in them that depends on a decision cites its number (`ADR-0001 Dn`).

One further question (D17) surfaced while deriving the architecture: how the Celery workers persist to PostgreSQL, given that the specification names the API as the only database writer and also has workers write derivatives, vectors and search documents. It is recorded here because the Phase 0 scaffold depends on the answer.

## The stack as specified

This part is not open. It is restated so the decision record stands on its own.

| Layer | Choice |
| --- | --- |
| Web | Next.js 15, TypeScript strict, App Router, Tailwind with custom design tokens, next-intl, OpenSeadragon with the IIIF plugin |
| API | FastAPI on Python 3.12, SQLAlchemy 2, Alembic, Pydantic v2 |
| Jobs | Celery workers with a Redis broker |
| Identity | Keycloak 26 (OIDC Authorization Code with PKCE, MFA, passkeys, SAML brokering) |
| Authorization | Cerbos policy engine, policies as versioned YAML with a test suite |
| Database | PostgreSQL 16 with pgvector, row-level security |
| Search | OpenSearch 2.x with the ICU analysis plugin and a custom Arabic analyzer |
| Cache | Redis 7 |
| Object storage | S3-compatible: MinIO locally and on-premises, AWS S3 or equivalent in cloud; preservation bucket with object lock |
| Image server | Cantaloupe 5 behind an authorizing proxy, pyvips visible watermarks, seeded spread-spectrum forensic watermarks |
| OCR, language models, embeddings, payments, messaging | Adapter interfaces with a real and a mock implementation each |
| Edge | Cloudflare in front of Caddy |
| Observability | OpenTelemetry to Grafana Loki, Tempo and Prometheus; Sentry |
| Runtime | Docker Compose for local and pilot, k3s manifests for production |

## Decisions

Each decision records the question from the specification, the specification default, the recommendation made in the first session, and the decision the owner confirmed in the first session on 2026-10-04.

### Summary

| # | Decision | Spec default | Recommendation | Status |
| --- | --- | --- | --- | --- |
| D1 | Product and repository name | `turath-platform` working name | Keep the repository name; `jdhp` as the technical short name | Confirmed: repository name, `jdhp` |
| D2 | Pilot hosting target | Cloud for the pilot | Default | Confirmed, default |
| D3 | Catalog conventions to mirror | Generic MARC 21, LCSH, local Arabic vocabulary | Default | Confirmed, default |
| D4 | Payment gateway | HyperPay sandbox | Default | Confirmed, default |
| D5 | OCR provider for the pilot | Azure AI Document Intelligence | Default | Confirmed, default |
| D6 | Language model providers | Claude API first, second with the institution | Default | Confirmed, default |
| D7 | Embedding model | Decided by the 100-query set in Phase 3 | Default | Confirmed, default |
| D8 | Translation specification session (TRN-8) | Before Phase 3 | Default, schedule during Phase 2 | Confirmed, default |
| D9 | Reviewer staffing | None (business decision) | Record when known; portal designed for N named reviewers | Confirmed: record when known |
| D10 | Persistent identifier scheme | ARK | ARK, test NAAN 99999 until the institution's NAAN exists | Confirmed, default |
| D11 | Paid access class in Phase 1 | Defer to Phase 2 | Default | Confirmed, default |
| D12 | Researcher verification documents | Passport or national ID, rights officer reviews | Default | Confirmed, default |
| D13 | Reading-room mode in the pilot | Not in scope | Default | Confirmed, default |
| D14 | Typeface pairing | Decide in Phase 0 from three rendered candidates | Default; three candidate pairings proposed below | Confirmed, default |
| D15 | Seed book | Fictional original text | Default, strongly | Confirmed, default |
| D16 | Retention periods | 7 years audit, 30 days identity documents, 2 years inactive accounts | Default, as configuration | Confirmed, default |
| D17 | Worker write path to PostgreSQL | Not in spec | Workers reuse the API package in-process under a restricted database role | Confirmed: option B |

### D1. Product and repository name

- Question: what the product and repository are called until the brand exists.
- Spec default: `turath-platform` as a working name, to be replaced by the brand.
- Recommendation: keep the GitHub repository name `Jordanian-Digital-Heritage-Platform` as it is and use a short technical name wherever a stable identifier is needed.
- Decision: Confirmed. The product and the repository are named Jordanian Digital Heritage Platform (Arabic: منصة التراث الأردني الرقمي), not the `turath-platform` working name. The technical short name is `jdhp`, the initials of the repository name: Python distributions `jdhp-api`, `jdhp-worker`, `jdhp-adapters`, `jdhp-metadata` with import names `jdhp_api` and so on; npm scope `@jdhp/*`; Compose project name, Kubernetes namespace and Keycloak realm `jdhp`; database roles `jdhp_app`, `jdhp_worker`, `jdhp_migrate`; Redis key prefix `jdhp:`.
- Consequences: package, realm and role names are fixed in Phase 0; a brand name later changes display strings only, which are externalized in both languages from the first commit.

### D2. Pilot hosting target

- Question: cloud region now and on-premises at handover, or on-premises from the start.
- Spec default: cloud for the pilot.
- Recommendation: default. The region decision stays with the institution because the content is a national asset. The platform's only cloud dependency is S3-compatible object storage, so the move at handover is a data copy, not a rewrite. Compose for the pilot, k3s manifests proven in Phase 4.
- Decision: Confirmed, default.

### D3. Catalog conventions to mirror first

- Question: which institution's MARC 21 export profile and subject vocabulary to mirror.
- Spec default: generic MARC 21 with Library of Congress Subject Headings plus a local Arabic vocabulary.
- Recommendation: default. This is a Phase 3 concern. Phase 0 only reserves vocabulary scheme identifiers (`lcsh`, `local-ar`, `gazetteer-jo`, `period-jo`, `material`) in the `vocabulary_term` model so a partner's scheme can be added as data.
- Decision: Confirmed, default.

### D4. Payment gateway

- Question: HyperPay, PayTabs, or another licensed Jordanian provider.
- Spec default: build the adapter against HyperPay's sandbox.
- Recommendation: default. The `PaymentGateway` interface and a mock implementation ship in Phase 0 so the grant model is complete; the HyperPay hosted-page implementation and webhook verification land in Phase 2. Hosted pages keep the platform out of PCI DSS scope (SEC-30).
- Decision: Confirmed, default.

### D5. OCR provider for the pilot

- Question: Azure AI Document Intelligence or Google Document AI.
- Spec default: Azure.
- Recommendation: default. Phase 0, Phase 1 and CI run the mock provider fed by the seed book's synthetic ALTO, so no Azure credential is needed until staging processes sample scans. Kraken remains the self-hosted option for manuscripts.
- Decision: Confirmed, default.

### D6. Language model providers

- Question: which providers sit behind the translation and search adapter.
- Spec default: Claude API first, a second provider chosen with the institution, a reserved self-hosted option.
- Recommendation: default. The adapter ships with `claude` and `mock` implementations in Phase 3 and a documented extension point for the second provider. Production configuration refuses any provider not on the no-training-on-inputs allowlist (TRN-6).
- Decision: Confirmed, default.

### D7. Embedding model

- Question: which multilingual embedding model.
- Spec default: a model with strong Arabic results, decided by the 100-query test set in Phase 3.
- Recommendation: default. From Phase 0 the `page_embedding` row records model and version so a later choice or change triggers a tracked re-embedding job (SRCH-6).
- Decision: Confirmed, default.

### D8. Translation specification session (TRN-8)

- Question: when register, style rules, evaluation method and acceptance thresholds are specified.
- Spec default: scheduled before Phase 3 starts.
- Recommendation: default; hold the session during Phase 2 so the glossary seeding and prompt templates can be built as soon as Phase 3 opens.
- Decision: Confirmed, default.

### D9. Reviewer staffing

- Question: how many reviewers and how many hours per week.
- Spec default: none; this is a business decision that sets how many books can carry translations.
- Recommendation: record the planned number of reviewers and weekly hours here when known. The review portal assigns tasks to named reviewers with due dates, and the throughput dashboard (REV-3) makes capacity visible, so the number can change without code changes. The demo uses two reviewer test accounts.
- Decision: Confirmed as recommended. Reviewers and weekly hours: to be recorded here when the institution sets them.

### D10. Persistent identifier scheme

- Question: ARK through a registered name assigning authority, or DOI through a registration agency.
- Spec default: ARK, lower cost and no per-item fee.
- Recommendation: ARK. Registration of a Name Assigning Authority Number (NAAN) is free, there is no per-item fee, and resolution can be hosted by the institution itself, which suits a national collection moving on-premises. Until the institution's NAAN is assigned, mint under the ARK test NAAN `99999`, which the ARK Alliance reserves for testing, with `ARK_NAAN` as configuration. Public names are opaque NOID-style strings with a check character; pages are qualified as `ark:/{naan}/{name}/p{seq}`. A DOI can be added later for works that need one, as a second identifier, never as a replacement.
- Decision: Confirmed, default.
- Consequences: fixes the Phase 0 `public_id` columns, the minter, the URL scheme (INT-7), the citation format (CAT-1, SRC-3) and the resolver route.

### D11. Paid access class in Phase 1

- Question: whether Phase 1 includes the Paid class or defers it to Phase 2 with Restricted.
- Spec default: defer, keep the demo focused on reading quality.
- Recommendation: default. The `access_class` enumeration includes `paid` from Phase 0 and the policies deny reading a Paid work without a grant, so nothing is reworked later.
- Decision: Confirmed, default.

### D12. Researcher verification

- Question: which identity documents are accepted and who reviews them.
- Spec default: passport or national ID, reviewed by a rights officer.
- Recommendation: default. Documents are stored in the `uploads` bucket under a dedicated key and deleted 30 days after the decision (ACC-3, SEC-23); only the Rights officer role can view them, through the API, with an audit event per view.
- Decision: Confirmed, default.

### D13. Reading-room mode

- Question: in scope for the pilot or not.
- Spec default: not.
- Recommendation: default. ACS-5 is a SHOULD. The model reserves `institution.ip_ranges` so it can be added without a migration of meaning.
- Decision: Confirmed, default.

### D14. Typeface pairing

- Question: Arabic and Latin typeface choices.
- Spec default: decide in Phase 0 after rendering three candidate pairings with real catalog records; record in `docs/DESIGN.md`.
- Recommendation: default. Proposed candidates for the rendering test, all open-licensed, self-hostable and subsettable per script:
  1. Amiri for Arabic reading text, Reem Kufi for Arabic display, Crimson Pro for Latin reading text, IBM Plex Sans Arabic for the interface (Arabic and Latin in one family).
  2. Scheherazade New for Arabic reading text, Aref Ruqaa for Arabic display, EB Garamond for Latin reading text, Vazirmatn for the interface.
  3. Noto Naskh Arabic for Arabic reading text, Noto Kufi Arabic for display, Noto Serif for Latin reading text, Noto Sans and Noto Sans Arabic for the interface. The single-superfamily option with guaranteed coverage.
  Kashida, ligatures and mixed-script catalog lines are verified in Chromium, Firefox and Safari before the pairing is committed to `docs/DESIGN.md`.
- Decision: Confirmed, default.

### D15. The seed book

- Question: an original fictional text written for the project, or a public-domain Jordanian text the team is certain is free of rights.
- Spec default: fictional.
- Recommendation: default, strongly, so that no demo ever raises a rights question and no real heritage material enters a fixture. Proposed shape: a fictional early twentieth-century Arabic chronicle of an invented town and its wadi, by an invented author, with an English title and description so the metadata translation path (TRN-5) has material. Forty pages covering every page type in the model: cover, title page, table of contents, text, an illustration, a map, a table, a colophon and endpapers, with synthetic scans and synthetic ALTO. Title and author names are checked against existing works before use.
- Decision: Confirmed, default.

### D16. Retention periods

- Question: audit and personal data retention, to be confirmed with the institution's legal counsel.
- Spec default: 7 years audit, 30 days identity documents after decision, 2 years for inactive member accounts.
- Recommendation: default, expressed as configuration values validated at startup, so counsel's answer is a configuration change with an ADR, not a code change.
- Decision: Confirmed, default.

### D17. Worker write path to PostgreSQL

- Question: `SPEC.md` names the API as the only database writer, has workers write derivatives, vectors and search documents, and its diagram connects workers to PostgreSQL. Two readings:
  - A. Workers persist through internal API endpoints over HTTP with a service token. The API process is literally the only writer.
  - B. Workers import the API's domain layer in-process and write through the same service functions under a restricted `jdhp_worker` database role. "Only writer" means one codebase and one set of write paths, not one process.
- Recommendation: B. One code path carries every invariant (REV-1 pending state, audit events, versioning), there is no internal HTTP surface to protect, and embeddings and OCR text never cross the network as request bodies. The second credential is mitigated by granting the worker role only the tables the pipeline writes, and by the architecture rule that routers and tasks never touch models directly, enforced by import-linter in CI.
- Decision: Confirmed, option B.
- Consequences: `apps/worker` is a thin Celery app depending on `jdhp-api` as a library, and the first migration creates the `jdhp_app`, `jdhp_worker` and `jdhp_migrate` roles with the worker role granted only the pipeline tables.

## Consequences

- Phase 0 scaffolding started on acceptance of this ADR.
- Any later change to a confirmed decision is a new ADR that supersedes the relevant row here.
- `docs/ARCHITECTURE.md` and `docs/THREAT_MODEL.md` were revised in the same change that accepted this ADR.

## Confirmation

Confirmed by the owner in the first session on 2026-10-04: every specification default, the repository name for D1 with `jdhp` as the technical short name, and option B for D17.
