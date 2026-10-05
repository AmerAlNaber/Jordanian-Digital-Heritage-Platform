# OpenSearch with the ICU analysis plugin the Arabic analyzer needs (CAT-4). The plugin is
# installed at build time so the official entrypoint runs unchanged at start.
ARG OPENSEARCH_VERSION=2.19.0
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}
RUN bin/opensearch-plugin install --batch analysis-icu
