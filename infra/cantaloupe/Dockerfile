# Cantaloupe 5 with OpenJPEG for JPEG 2000. Internal service: reachable only from the tile gateway.
FROM eclipse-temurin:21-jre-jammy

ARG CANTALOUPE_VERSION=5.0.6
RUN apt-get update && apt-get install -y --no-install-recommends \
      libopenjp2-tools gettext-base unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/cantaloupe.zip \
      "https://github.com/cantaloupe-project/cantaloupe/releases/download/v${CANTALOUPE_VERSION}/cantaloupe-${CANTALOUPE_VERSION}.zip" \
    && unzip -q /tmp/cantaloupe.zip -d /opt \
    && mv "/opt/cantaloupe-${CANTALOUPE_VERSION}" /opt/cantaloupe \
    && rm /tmp/cantaloupe.zip
RUN useradd --system --uid 10001 --home /opt/cantaloupe cantaloupe \
    && mkdir -p /var/cache/cantaloupe /etc/cantaloupe \
    && chown -R cantaloupe:cantaloupe /var/cache/cantaloupe /etc/cantaloupe
COPY cantaloupe.properties.template delegates.rb entrypoint.sh /opt/jdhp/
RUN chmod +x /opt/jdhp/entrypoint.sh
USER cantaloupe
EXPOSE 8182
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8182/health || exit 1
ENTRYPOINT ["/opt/jdhp/entrypoint.sh"]
