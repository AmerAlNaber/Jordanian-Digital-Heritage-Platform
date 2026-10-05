# ADR-0005: Image source behind the tile gateway

Status: proposed (2026-10-05), awaiting the owner's decision

## Context

`SPEC.md` names Cantaloupe as the IIIF image server and `docs/ARCHITECTURE.md` puts the authorizing tile gateway in front of it: the gateway checks the grant, caps the response, fetches the region from Cantaloupe with a signed internal header, and applies the marks. Phase 0 found that the Cantaloupe 5.0.7 release bundles Java libraries with fixable vulnerabilities, so its image is scanned for operating system packages only (ADR-0004, item 3). The gateway itself (task 18) runs libvips for the marks, and libvips reads the JPEG 2000 access derivatives the pipeline already writes, so the gateway can cut the region itself.

The gateway therefore ships with an `ImageSource` interface and two implementations, selected by `JDHP_IMAGE_SOURCE`:

- `cantaloupe` (default): proxies region requests to Cantaloupe over the internal network with the `X-Jdhp-Image-Auth` header its delegate script verifies (ARCHITECTURE 8.1).
- `libvips`: reads the derivative from the access bucket and crops, scales and rotates it with libvips in the gateway process.

Both honour the same request validation, pixel cap, marks, rate limits and cache rules; the gateway tests run the `libvips` source and the Compose stack runs `cantaloupe`.

## Options

1. **Keep Cantaloupe, build it from source with current dependencies.** Keeps the component named in the specification and its mature JPEG 2000 and pyramid handling (OpenJPEG, chunked S3 reads, derivative caches). Costs a Gradle build in Docker with dependency pins to maintain, a second image to patch, and the JVM's memory in every deployment. The delegate script and the signed header stay.
2. **Run the `libvips` source and remove Cantaloupe from the stack.** One process fewer, no bundled Java libraries to accept or rebuild, the full Trivy scan scope restored, and the same libvips the derivatives and marks already use. Costs: the gateway reads whole derivatives from the bucket per request until a region cache is added (libvips decodes only the JPEG 2000 resolution level it needs, but the object is fetched in full), and it deviates from a component named in `SPEC.md`, which needs the owner's approval.
3. **Keep Cantaloupe as released** with the reduced scan scope. Rejected: SEC-18 asks for scanned, patched images, and the exception was meant to be temporary.

## Recommendation

Option 2 for the pilot, with a per-page derivative cache in the gateway (bounded, on local disk, keyed by derivative checksum) before load testing; option 1 remains available by setting `JDHP_IMAGE_SOURCE=cantaloupe` and building the hardened image if the owner prefers the named server. The `libvips` source is the one the gateway's tests prove; the Cantaloupe source is exercised by the Compose integration job.

## Decision

Pending. Until the owner decides, Compose keeps `cantaloupe` as the default so the stack matches the specification, and both sources remain supported.

## Consequences (when decided)

- Option 1: add the Gradle build stage to `infra/cantaloupe/Dockerfile`, pin the vulnerable dependencies to fixed versions, restore `scan: os,library` for the image in CI, and remove the exception from `CHANGELOG.md`.
- Option 2: set `JDHP_IMAGE_SOURCE=libvips` as the default, drop the `cantaloupe` service, delegate script and image from Compose, the k3s manifests and CI, add the gateway's derivative cache, and record the deviation from `SPEC.md` here.
