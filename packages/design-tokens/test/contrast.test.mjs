// ACX-4: text contrast of at least 4.5 to 1 in both themes; focus is not carried by color alone.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { contrast } from "../src/oklch.mjs";

const tokens = JSON.parse(readFileSync(new URL("../tokens.json", import.meta.url), "utf8"));

for (const mode of ["light", "dark"]) {
  const c = tokens.color[mode];
  test(`${mode}: ink on background and surface meets 4.5:1`, () => {
    for (const bg of ["background", "surface", "surface-raised"]) {
      assert.ok(
        contrast(c.ink, c[bg]) >= 4.5,
        `ink on ${bg}: ${contrast(c.ink, c[bg]).toFixed(2)}`,
      );
      assert.ok(
        contrast(c["ink-muted"], c[bg]) >= 4.5,
        `ink-muted on ${bg}: ${contrast(c["ink-muted"], c[bg]).toFixed(2)}`,
      );
    }
  });
  test(`${mode}: accent text on background and accent-ink on accent meet 4.5:1`, () => {
    assert.ok(contrast(c.accent, c.background) >= 4.5, contrast(c.accent, c.background).toFixed(2));
    assert.ok(
      contrast(c["accent-ink"], c.accent) >= 4.5,
      contrast(c["accent-ink"], c.accent).toFixed(2),
    );
  });
  test(`${mode}: provenance labels are legible on the background`, () => {
    for (const label of ["label-scan", "label-human", "label-ai"]) {
      assert.ok(
        contrast(c[label], c.background) >= 4.5,
        `${label}: ${contrast(c[label], c.background).toFixed(2)}`,
      );
    }
  });
  test(`${mode}: hairlines are visible but quiet (at least 1.3:1, under 3:1)`, () => {
    const ratio = contrast(c.hairline, c.background);
    assert.ok(ratio >= 1.3 && ratio < 3, ratio.toFixed(2));
  });
}

test("the type scale has seven steps and reading text reaches 18px on desktop", () => {
  const steps = Object.keys(tokens.type.steps);
  assert.equal(steps.length, 7);
  const reading = tokens.type.steps[tokens.type["reading-step"]];
  assert.ok(Number.parseFloat(reading.max) * 16 >= 18, reading.max);
});

test("radius and elevation follow the archival rule", () => {
  assert.equal(tokens.radius.image, "0px");
  assert.equal(tokens.radius.frame, "0px");
  assert.equal(tokens.radius.control, "2px");
  assert.equal(tokens.elevation.none, "none");
});
