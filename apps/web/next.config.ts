import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  images: { formats: ["image/webp"], remotePatterns: [] },
  experimental: { optimizePackageImports: ["next-intl"] },
  async rewrites() {
    // Development without the Caddy proxy: send the API and tile paths to the local services so the
    // browser stays same-origin and the Content Security Policy holds. Deployments leave these unset.
    const api = process.env.JDHP_DEV_API_URL;
    const tiles = process.env.JDHP_DEV_TILES_URL;
    const afterFiles = [];
    if (api) afterFiles.push({ source: "/api/:path*", destination: `${api.replace(/\/$/, "")}/:path*` });
    if (tiles) afterFiles.push({ source: "/iiif/:path*", destination: `${tiles.replace(/\/$/, "")}/iiif/:path*` });
    return { beforeFiles: [], afterFiles, fallback: [] };
  },
  async headers() {
    // Security headers that do not depend on a per-request nonce; the CSP is set in middleware (SEC-16).
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default withNextIntl(config);
