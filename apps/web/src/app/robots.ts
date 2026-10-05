import type { MetadataRoute } from "next";

// SEO-5: AI crawlers are welcome on open metadata and blocked on the reader, accounts and admin.
const AI_CRAWLERS = [
  "GPTBot",
  "ClaudeBot",
  "Google-Extended",
  "PerplexityBot",
  "CCBot",
  "Applebot-Extended",
];
const PUBLIC = [
  "/ar/",
  "/en/",
  "/ar/catalog",
  "/en/catalog",
  "/ar/works/",
  "/en/works/",
  "/ar/collections",
  "/en/collections",
  "/ar/subjects/",
  "/en/subjects/",
  "/llms.txt",
];
const PRIVATE = [
  "/ar/read/",
  "/en/read/",
  "/ar/account",
  "/en/account",
  "/ar/admin",
  "/en/admin",
  "/ar/review",
  "/en/review",
  "/api/",
  "/iiif/",
];

export default function robots(): MetadataRoute.Robots {
  const base = process.env.NEXT_PUBLIC_BASE_URL ?? "http://localhost:8080";
  return {
    rules: [
      { userAgent: "*", allow: PUBLIC, disallow: PRIVATE },
      ...AI_CRAWLERS.map((userAgent) => ({ userAgent, allow: PUBLIC, disallow: PRIVATE })),
    ],
    sitemap: `${base}/sitemap.xml`,
  };
}
