# ADR-0008: Print rendering and delivery

Status: accepted (2026-10-05)

## Context

RDR-4 requires print to be a server-rendered, watermarked, low-resolution PDF of up to a staff-set page quota per grant, logged with page numbers. SEC-11 requires the visible and forensic marks on every print PDF, with the user, grant and timestamp, and SEC-15 requires download URLs that expire in fifteen minutes and work once. The spec's Phase 1 acceptance has a member print two pages of the seed book and find the action in the audit viewer.

## Decisions

1. **Rendering runs in the worker**, as a task on the derivatives queue. Rendering twenty pages decodes twenty JPEG 2000 derivatives; that belongs beside the other image work, not in an API request. The API records the job, reserves the pages and returns `202`; the browser polls the job and asks for a link when it is ready. The rendering code lives in the reader module (`jdhp_api.modules.reader.printing`) and the worker calls it, as the rest of the pipeline reuses the API package (ADR-0001 D17).
2. **The platform writes its own PDF.** Each page is one JPEG embedded as an image XObject with the DCTDecode filter, so the marked pixels the renderer produced are exactly what the file holds. The writer is eighty lines with no dependency; the API and worker images carry no PDF engine to scan or patch. A PDF library is a test dependency only (pypdf), used to read what the writer produces.
3. **Resolution.** Pages are scaled so their longest edge is at most 1754 pixels (A4 at 150 ppi) and never upscaled; the PDF declares 150 ppi for every page, so a print comes out at document size. Both are settings (`JDHP_PRINT_PPI`, `JDHP_PRINT_MAX_EDGE_PX`).
4. **Marks.** The visible mark carries the user tag, the grant's public name, the work's public name and the time, at a size made for a whole page rather than a tile. The forensic mark uses the reader session's key, so a leaked PDF is traced the same way a leaked tile is (ADR-0006).
5. **Pages come from the access derivative through the libvips source**, whatever the tile gateway's image source setting, since the worker has the bucket and the libraries and the job is batch work with no latency target. ADR-0005 stays about the interactive tile path.
6. **Quota is counted from the jobs.** A grant's used pages are the pages of every job that is not failed. The worker never updates the grant row; a failed render gives its pages back by marking the job failed. `grant.print_used` is kept in step by the API for reporting.
7. **Delivery.** The owner mints a link; the API stores the SHA-256 of a random 32-byte token with a fifteen-minute expiry. The file route authorizes on the token alone (the policy allows `download` to anyone whose token is valid), so the browser can open the link without an Authorization header. The row is locked while the file is handed over, the state moves to downloaded, the token hash is cleared and the object is deleted. A second request with the same token is refused.
8. **Policy.** `print` on a work now requires a grant holder on a published, unfrozen Open, Registered or Paid work. The grant carries the quota, so an anonymous reader of an Open work cannot print; a signed-in member has a class grant from the moment they open the reader (ADR-0007).

## Consequences

- A print needs a worker running. The seed stack has one; the integration job can print once the end-to-end suite signs in.
- Print PDFs are plain raster PDFs: no text layer, no search, no selection, which is what CAT-4 asks for.
- The exports bucket's one-day lifecycle rule remains the backstop for jobs whose link was never used.
- Staff quotas, Paid grants and institutional grants (Phase 2) reuse the same job model; `print_job` gains nothing new for them.
