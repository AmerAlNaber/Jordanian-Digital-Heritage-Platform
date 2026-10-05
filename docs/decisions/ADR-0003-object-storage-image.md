# ADR-0003: Object storage image built from source

Status: accepted (2026-10-05)

## Context

`SPEC.md` names MinIO as the S3-compatible object store for local development and on-premises deployments, with the preservation bucket under object lock and versioning. In 2025 MinIO withdrew its container images from Docker Hub and quay.io; the pinned releases the Compose stack referenced can no longer be pulled, which stopped the stack in CI. The source remains published under the AGPL with release tags.

## Options

1. Build MinIO and its client `mc` from the pinned source releases in our own image.
2. Replace MinIO with another S3-compatible store that still publishes images (Garage, SeaweedFS, Versity Gateway, Zenko CloudServer).
3. Depend on a third-party rebuild of MinIO images.

## Decision

Option 1. `infra/compose/minio/Dockerfile` builds `minio` and `mc` from the release tags given as build arguments, on the official Go image, into a Debian slim runtime that applies security updates at build time, runs as a non-root user and answers the standard health endpoint. The Compose stack and the MinIO init job use this image; CI builds and scans it like every other image (SEC-18).

Option 2 changes a named component of the specification, which needs the owner's decision, not a CI fix; it also replaces the init script's `mc` commands for buckets, object lock, retention, users and policies. Option 3 trusts an unknown publisher with the store that holds the preservation copies.

## Consequences

- The first `compose up` compiles two Go programs, which takes several minutes; later starts reuse the cached image.
- The platform owns the image's security updates: the release tags are bumped like any other pinned dependency, and Trivy blocks on fixed high and critical findings in the Go binaries and the base image. Because upstream stopped releasing, the Dockerfile raises the Go modules Trivy names to their fixed versions before compiling; each raise is verified by building both programs, and the list is revisited whenever the scan reports a new fixed finding.
- Production deployments on k3s may use the institution's S3-compatible service instead; the bucket layout, object lock and the two credentials stay the same.
- If MinIO's source releases stop as well, option 2 becomes a decision for the owner, recorded in a new ADR.
