// The committed OpenAPI document must describe the routes the web app depends on and never a text field.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const doc = JSON.parse(readFileSync(new URL("../openapi.json", import.meta.url), "utf8"));

test("the document is the platform API", () => {
  assert.equal(doc.info.title, "Jordanian Digital Heritage Platform API");
  for (const path of [
    "/works",
    "/works/{name}",
    "/works/{name}/pages",
    "/collections",
    "/me",
    "/resolve/{name}",
  ]) {
    assert.ok(doc.paths[path], `missing ${path}`);
  }
});

test("no public schema carries OCR text (CAT-4)", () => {
  const offenders = [];
  for (const [name, schema] of Object.entries(doc.components.schemas)) {
    if (name === "ReviewTaskOut") continue;
    for (const field of Object.keys(schema.properties ?? {})) {
      if (["ocr_text", "alto", "text"].includes(field)) offenders.push(`${name}.${field}`);
    }
  }
  assert.deepEqual(offenders, []);
});
