# ADR-0006: Forensic watermark scheme

Status: accepted (2026-10-05)

## Context

Every protected tile and print page must carry, besides the visible mark, an invisible mark seeded per reader session so a leaked page can be traced to a user, a grant and a time (SEC-11, RDR-2). `docs/ARCHITECTURE.md` section 8.2 describes a spread-spectrum mark seeded from a per-session key derived with HKDF from the master key (the derivation is in ADR-0007) and asks for the library to be chosen on a test set of tiles, with the detector shipped as a staff tool in `apps/worker`.

## Options

1. **`invisible-watermark`** (DWT-DCT and RivaGAN methods). Needs OpenCV and, for RivaGAN, PyTorch: hundreds of megabytes in the gateway image and a runtime that is unsafe to load in forked workers. Payload-oriented (bits), not key-oriented.
2. **`blind-watermark`** (DWT-DCT-SVD). Needs OpenCV and PyWavelets; strong against some geometric attacks, slow per image (seconds), unmaintained releases.
3. **An in-house blind spread-spectrum mark in the 8 by 8 block DCT of the luminance, written with numpy.** Twelve mid-band coefficients per block are nudged in the direction of a pseudo-random sign pattern seeded by the session key; the detector correlates the coefficients with the pattern and reports a z-score. No image library beyond libvips and numpy, deterministic per key, about a hundred milliseconds per 512 pixel tile.

## Evaluation

Eighty 512 pixel tiles cut from the forty seed pages (two positions each), after the visible session mark, embedded with one key, scored with the detector (z-score; threshold 6):

| Condition | Detected | Lowest score | Median score |
| --- | --- | --- | --- |
| As served | 80/80 | 174.9 | 264.1 |
| WebP quality 80 (the reader's format) | 80/80 | 28.8 | 33.2 |
| WebP quality 60 | 80/80 | 14.0 | 16.3 |
| JPEG quality 75 | 80/80 | 42.0 | 52.5 |
| Converted to grayscale | 80/80 | 172.3 | 261.6 |
| Wrong key | 0/80 | -2.2 | -1.1 |
| Unmarked tile, right key | 0/80 | -2.0 | 0.6 |
| Crop at a block boundary (64, 128) | 0/80 | -1.5 | -0.3 |
| Crop off the block grid | 0/80 | -1.9 | 0.1 |
| Scaled to 90 percent | 0/80 | -2.0 | -0.5 |

Mean absolute pixel change 1.2 (of 255), maximum 32 on hard edges; not visible beside the visible mark. Embedding: 104 ms median per tile on the development machine.

## Decision

Option 3, implemented in `apps/api/src/jdhp_api/modules/reader/forensic.py` and applied by the tile gateway to every protected tile after the visible mark; print pages (task 21) use the same function per page. The detector is `python -m jdhp_worker.tools.detect_mark`, which re-derives candidate keys from the master key and the session rows and prints z-scores without printing any key.

## Consequences and known limit

- A leaked tile saved from the reader, re-encoded, recoloured or converted to grayscale is traced to its session with a wide margin and no false positive at the threshold.
- The pattern is laid over the tile's own 8 by 8 grid, so a crop that is not aligned to that grid, a rescaled copy or a screenshot of a zoomed viewer defeats the detector as it stands. The next step, scheduled with the reader hardening before Phase 4, is a synchronization search in the detector: try block-aligned offsets and a small set of scales, and lay the pattern over page coordinates so stitched tiles share one grid. The visible mark covers the gap meanwhile, and the threat model already states that watermarks make leaks traceable, not impossible.
- Embedding cost is paid per tile on the gateway; a derivative cache for the cut region (ADR-0005) would let the gateway mark cached regions and keep the first tile under the PRF-2 budget.
