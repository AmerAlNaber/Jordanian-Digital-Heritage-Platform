# ADR-0004: Phase 0 closure decisions

Status: accepted (2026-10-05)

## Context

Phase 0 (foundation) met its acceptance criteria in CI and was merged to `main` in pull request #1: the Compose stack starts every service, the seed book is ingested through the real pipeline with the mock OCR provider, and the route-coverage test passes with zero unprotected routes. Closing the phase left a handful of items that needed the owner's decision before Phase 1 (public catalog and secure reader) began. The owner reviewed the running platform and decided them on 2026-10-05.

## Decisions

1. **Persistent identifiers keep the ARK test Name Assigning Authority Number `99999` until handover.** Registering the institution's own number is a handover task (Phase 4). The number is one configuration value (`JDHP_ARK_NAAN`); names minted under the test number are regenerated when the real number arrives, so no demo link is promised as permanent. Supersedes nothing in ADR-0001 D10, which already assumed ARK.
2. **Typefaces are confirmed as recorded in `docs/DESIGN.md`**: Amiri for Arabic reading text, Noto Kufi Arabic for Arabic display, Crimson Pro for Latin reading text, IBM Plex Sans Arabic for the interface and IBM Plex Mono for identifiers. The pairing was judged on the rendered seed record and the running catalog. The owner may revisit it at a later stage; the Firefox and Safari kashida pass owed before Phase 1 closes still stands.
3. **The Cantaloupe image server question is decided with the tile gateway work, in ADR-0005.** The image is scanned for operating system packages only until then. The options are a source build of Cantaloupe 5.0.7 with current dependencies, or an IIIF Image API 3.0 implementation on libvips inside the tile gateway; the second deviates from the server named in `SPEC.md` and needs the owner's explicit approval when proposed.
4. **MinIO stays built from the pinned source releases (ADR-0003).** No further action.
5. **The two accepted advisories stand with their written reasons** (picomatch inside Next.js in `.trivyignore`; the development-only `braces` advisory in `pnpm.auditConfig.ignoreGhsas`). They are reviewed in the monthly dependency window (SEC-18) and removed when fixes ship.
6. **Pipeline failures must be visible on the intake batch.** A derivative, OCR or embedding task that fails records the failure on the batch (`failed` with a readable reason) and as a PREMIS event, instead of leaving the batch in `validating`. A single page failure fails the batch: ADM-1 says an intake fails with a reason, and a partially processed object must not look like a stalled one. Re-running the package task after the cause is fixed re-validates the batch and completes the remaining pages.

## Consequences

- Phase 1 starts from the merged `main`. Work continues on the same development branch, restarted from `main`, and reaches `main` through squash-merged pull requests as before.
- ADR-0005 (image source) and ADR-0006 (forensic watermark library) are due during Phase 1, as `docs/ARCHITECTURE.md` section 18 lists.
- The ARK number and the typeface review are tracked as handover and later-stage items respectively; neither blocks a phase gate.
