#!/usr/bin/env sh
# Apply the index templates to OpenSearch. Idempotent; run on every deploy and at compose start.
set -eu
: "${OPENSEARCH_URL:?set OPENSEARCH_URL}"
AUTH=""
if [ -n "${OPENSEARCH_USER:-}" ]; then AUTH="-u ${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}"; fi
dir="$(dirname "$0")/templates"
until curl -fsS $AUTH "${OPENSEARCH_URL}/_cluster/health?wait_for_status=yellow&timeout=5s" >/dev/null 2>&1; do
  echo "waiting for opensearch"; sleep 3
done
for name in pages works; do
  curl -fsS $AUTH -X PUT "${OPENSEARCH_URL}/_index_template/jdhp-${name}" \
    -H 'Content-Type: application/json' --data-binary "@${dir}/${name}.json" >/dev/null
  echo "applied index template jdhp-${name}"
done
