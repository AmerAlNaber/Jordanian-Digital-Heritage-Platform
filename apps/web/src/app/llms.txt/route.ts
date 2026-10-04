// SEO-5: a plain-text description of the collection, the open API and the citation format.
export function GET() {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:8080";
  const body = `# Jordanian Digital Heritage Platform

> A secure digital library for a protected Jordanian heritage collection. Catalog metadata is open;
> scanned pages of protected works are served to signed-in readers as watermarked tiles only.

## What is open
- Catalog records in Arabic and English: ${base}/ar/catalog and ${base}/en/catalog
- Open JSON API (public records, Dublin Core and Schema.org shapes): ${base}/api/works
- Persistent identifiers: ARK, resolved at ${base}/ark:/<naan>/<name>

## What is not open
- OCR text of any work, and page images of protected works.

## Citation format
Author. Title. Date. ark:/<naan>/<name>  (every public record carries its ARK)

## Contact
See ${base}/en for the institution's contact details.
`;
  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
