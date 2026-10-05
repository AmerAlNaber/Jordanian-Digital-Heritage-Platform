# Design

Status: Phase 0 decisions, recorded as `SPEC.md` ("Visual identity and UX direction") requires. The
tokens live in `packages/design-tokens/tokens.json` and are built to CSS variables and a Tailwind
preset; this document explains the choices. Later phases add component patterns and screen notes.

## Direction

A serious archive, beautifully lit. Editorial, quiet, confident, timeless. The book is the hero: page
images get the most space and the most care, and the interface recedes behind hairlines and type.
Nothing here borrows from app stores or shops: no hero banners, no feature cards, no gradients,
no glass, no icons as decoration. Every piece of content says what it is, and the label system
(original scan, transcription, editorial note, AI-generated and reviewed) is part of the identity.

## Typography (ADR-0001 D14)

Three candidate pairings were rendered with the seed catalog record in Chromium on 2026-10-04:
`docs/design/typeface-pairings-2026-10-04.png` (source: `docs/design/typeface-pairings-sheet.html`).

| Role | Decision | Why | Fallbacks |
| --- | --- | --- | --- |
| Arabic reading text | **Amiri** | The strongest Naskh reading quality of the three at paragraph size: correct kashida, ligatures and mark placement, a classic print voice that suits a national library. Regular and Bold cover reading needs. | Scheherazade New, Noto Naskh Arabic |
| Arabic display | **Noto Kufi Arabic** | In the render, Reem Kufi misplaced vowel marks in the title (`أخبار بلدة سُمَيْرة`); Noto Kufi Arabic set the same title cleanly, has a full variable weight range and pairs with Amiri by contrast of structure (Kufi over Naskh), not by sameness. | Reem Kufi |
| Latin reading text | **Crimson Pro** | Matches Amiri's x-height and stroke contrast better than Noto Serif (too heavy) or EB Garamond (too light at 18 px); variable weight. Transliterations and English records sit comfortably inside Arabic lines. | Noto Serif, Georgia |
| Interface | **IBM Plex Sans Arabic** | Arabic and Latin in one family, quiet in controls and metadata labels, three weights. | IBM Plex Sans, system-ui |
| Monospace (identifiers, codes) | IBM Plex Mono | ARK identifiers and checksums in staff screens. | ui-monospace |

Rules: Arabic reading text is set 8 percent larger than Latin at the same step (`--arabic-scale`),
line height 1.75 for reading, measure 66ch. Fonts are self-hosted from `apps/web/public/fonts`,
subset per script and preloaded (PRF-5, INT-3). All faces are under the SIL Open Font License; the
licence files ship with the fonts.

Verification still owed before Phase 1 closes: a manual pass of kashida and ligature rendering in
Firefox and Safari on the catalog and reader screens (the Chromium pass is the render above).

## Type scale

Seven fluid steps between a 360 px phone and a 1440 px desktop, built as `clamp()` expressions:

| Step | Phone | Desktop | Use |
| --- | --- | --- | --- |
| -2 | 12.5 px | 13.4 px | Captions, legal lines |
| -1 | 14 px | 15.2 px | Metadata labels, table cells |
| 0 | 16 px | 17 px | Interface text, forms |
| 1 | 17 px | 20 px | Reading text (never under 18 px on desktop) |
| 2 | 20 px | 24 px | Record titles in lists |
| 3 | 24 px | 32 px | Page titles |
| 4 | 32 px | 44 px | Display, home statement |

## Color

Defined in OKLCH from the material: parchment, stone, ink and bronze, with one deep accent drawn
from Jordanian textile (madder red, hue 25) and one amber for rights notices. Light and dark themes
derive from the same hues; dark is a lit reading room, not an inversion.

| Token | Light | Dark | Role |
| --- | --- | --- | --- |
| background | oklch(97% 0.012 75) | oklch(17% 0.012 60) | Page |
| surface | oklch(94.5% 0.015 75) | oklch(21% 0.014 60) | Rails, panels |
| ink | oklch(24% 0.02 60) | oklch(93% 0.012 80) | Text |
| ink-muted | oklch(45% 0.018 60) | oklch(72% 0.014 75) | Metadata |
| hairline | oklch(85% 0.012 75) | oklch(31% 0.012 60) | Rules and borders |
| accent | oklch(41% 0.12 25) | oklch(72% 0.11 25) | The one action, links, focus |
| bronze | oklch(52% 0.075 70) | oklch(70% 0.08 70) | Secondary emphasis, provenance marks |
| warning | oklch(55% 0.13 75) | oklch(78% 0.13 80) | Rights notices |
| label-scan, label-human, label-ai | muted, green, violet | lighter variants | The provenance label system (SRC-1) |

Every text token meets 4.5:1 on its backgrounds in both themes; `packages/design-tokens/test`
proves it on every build (ACX-4). Focus states use a 2 px accent ring plus an offset, never color
alone.

## Space, shape, elevation, motion

- Spacing on an 8-point grid (`--space-1` to `--space-24`); section rhythm at 64, 128 and 192.
- Radius 2 px on controls, 0 on images and frames. Archival objects are not rounded.
- No elevation anywhere except the reader's floating toolbar, which carries one soft shadow.
- Motion only where it carries meaning: a 180 ms fade on tile load and a 320 ms page turn, both
  removed when the user prefers reduced motion.

## The label system

Every secondary content frame opens with a label in the interface face at step -1:

- Original scan: muted ink, no icon. The page itself.
- Transcription, translation, editorial note by a person: green label text, "prepared by a person".
- AI-generated: violet label text, "produced by an AI model, reviewed by [name] on [date]". Never
  shown without a reviewer and a date, because it is never public before approval (REV-1).

## Screens

Phase 1 adds notes per key screen (home, catalog and search, book page, reader, request and
approval, review portal, admin) with layout decisions. Until then the principles above and the
spec's table of key screens are the brief.
