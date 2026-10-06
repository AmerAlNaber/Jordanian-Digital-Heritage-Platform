#!/usr/bin/env sh
# Buckets, lifecycle rules and the two credentials: the app credential never writes preservation.
# The app credential may also stat objects (GetObjectAttributes) in the buckets it can already read:
# S3 clients use it before a ranged read, and it reveals nothing GetObject does not.
set -eu
: "${MINIO_ROOT_USER:?}"; : "${MINIO_ROOT_PASSWORD:?}"
: "${JDHP_S3_ACCESS_KEY:?}"; : "${JDHP_S3_SECRET_KEY:?}"; : "${JDHP_S3_INGEST_ACCESS_KEY:?}"; : "${JDHP_S3_INGEST_SECRET_KEY:?}"
until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do echo "waiting for minio"; sleep 2; done
P=${JDHP_BUCKET_PRESERVATION:-jdhp-preservation}; A=${JDHP_BUCKET_ACCESS:-jdhp-access}; U=${JDHP_BUCKET_UPLOADS:-jdhp-uploads}
E=${JDHP_BUCKET_EXPORTS:-jdhp-exports}; L=${JDHP_BUCKET_AUDIT_ARCHIVE:-jdhp-audit-archive}
mc mb --ignore-existing --with-lock "local/$P"
mc retention set --default COMPLIANCE 3650d "local/$P" >/dev/null 2>&1 || true
mc version enable "local/$P"
mc mb --ignore-existing "local/$A"; mc version enable "local/$A"
mc mb --ignore-existing "local/$U"; mc mb --ignore-existing "local/$E"
mc mb --ignore-existing --with-lock "local/$L"; mc retention set --default COMPLIANCE 2555d "local/$L" >/dev/null 2>&1 || true
mc ilm rule add --expire-days 30 "local/$U" >/dev/null 2>&1 || true
mc ilm rule add --expire-days 1 "local/$E" >/dev/null 2>&1 || true
cat > /tmp/app-policy.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetObject","s3:GetObjectAttributes","s3:PutObject","s3:DeleteObject","s3:ListBucket","s3:GetBucketLocation"],
  "Resource":["arn:aws:s3:::$A","arn:aws:s3:::$A/*","arn:aws:s3:::$U","arn:aws:s3:::$U/*","arn:aws:s3:::$E","arn:aws:s3:::$E/*"]},
 {"Effect":"Allow","Action":["s3:PutObject","s3:ListBucket","s3:GetBucketLocation"],"Resource":["arn:aws:s3:::$L","arn:aws:s3:::$L/*"]}
]}
JSON
cat > /tmp/ingest-policy.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:ListBucket","s3:GetBucketLocation","s3:GetObjectRetention"],
  "Resource":["arn:aws:s3:::$P","arn:aws:s3:::$P/*"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket","s3:GetBucketLocation"],
  "Resource":["arn:aws:s3:::$A","arn:aws:s3:::$A/*","arn:aws:s3:::$U","arn:aws:s3:::$U/*"]}
]}
JSON
mc admin policy create local jdhp-app /tmp/app-policy.json >/dev/null 2>&1 || true
mc admin policy create local jdhp-ingest /tmp/ingest-policy.json >/dev/null 2>&1 || true
mc admin user add local "$JDHP_S3_ACCESS_KEY" "$JDHP_S3_SECRET_KEY" >/dev/null 2>&1 || true
mc admin user add local "$JDHP_S3_INGEST_ACCESS_KEY" "$JDHP_S3_INGEST_SECRET_KEY" >/dev/null 2>&1 || true
mc admin policy attach local jdhp-app --user "$JDHP_S3_ACCESS_KEY" >/dev/null 2>&1 || true
mc admin policy attach local jdhp-ingest --user "$JDHP_S3_INGEST_ACCESS_KEY" >/dev/null 2>&1 || true
echo "buckets, lifecycle rules and credentials ready"
