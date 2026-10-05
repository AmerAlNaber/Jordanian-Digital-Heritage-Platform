#!/usr/bin/env bash
set -euo pipefail
: "${JDHP_S3_ENDPOINT_URL:?}"; : "${JDHP_S3_ACCESS_KEY:?}"; : "${JDHP_S3_SECRET_KEY:?}"
: "${JDHP_BUCKET_ACCESS:?}"; : "${JDHP_IMAGE_INTERNAL_KEY:?}"
export JDHP_S3_REGION="${JDHP_S3_REGION:-us-east-1}"
envsubst '${JDHP_S3_ENDPOINT_URL} ${JDHP_S3_ACCESS_KEY} ${JDHP_S3_SECRET_KEY} ${JDHP_S3_REGION} ${JDHP_BUCKET_ACCESS}' \
  < /opt/jdhp/cantaloupe.properties.template > /etc/cantaloupe/cantaloupe.properties
cp /opt/jdhp/delegates.rb /etc/cantaloupe/delegates.rb
exec java -Dcantaloupe.config=/etc/cantaloupe/cantaloupe.properties -Xms256m -Xmx"${CANTALOUPE_HEAP:-1g}" \
  -jar /opt/cantaloupe/cantaloupe-*.jar
