# Web image: pnpm workspace build, Next.js standalone output, non-root runtime.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/schemas/package.json packages/schemas/package.json
COPY packages/design-tokens/package.json packages/design-tokens/package.json
COPY tests/e2e/package.json tests/e2e/package.json
RUN pnpm install --frozen-lockfile --filter @jdhp/web...
COPY apps/web apps/web
COPY packages/schemas packages/schemas
COPY packages/design-tokens packages/design-tokens
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @jdhp/schemas generate && pnpm --filter @jdhp/web build

FROM node:22-alpine AS runtime
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
       /opt/yarn* /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && addgroup -S jdhp && adduser -S -G jdhp -u 10003 jdhp
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=jdhp:jdhp /app/apps/web/.next/standalone ./
COPY --from=build --chown=jdhp:jdhp /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=jdhp:jdhp /app/apps/web/public ./apps/web/public
USER jdhp
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD wget -qO- http://127.0.0.1:3000/health >/dev/null || exit 1
CMD ["node", "apps/web/server.js"]
