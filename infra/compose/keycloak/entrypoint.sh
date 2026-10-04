#!/usr/bin/env bash
# Render the realm template with environment values, then start Keycloak with import.
set -euo pipefail
: "${KC_FRONTEND_URL:?set KC_FRONTEND_URL}"
: "${KC_WEB_CLIENT_SECRET:?set KC_WEB_CLIENT_SECRET}"
: "${KC_STAFF_CLIENT_SECRET:?set KC_STAFF_CLIENT_SECRET}"
export KC_SSL_REQUIRED="${KC_SSL_REQUIRED:-external}"
export KC_SMTP_HOST="${KC_SMTP_HOST:-mailpit}"
export KC_SMTP_PORT="${KC_SMTP_PORT:-1025}"
export KC_SMTP_FROM="${KC_SMTP_FROM:-noreply@localhost}"
mkdir -p /opt/keycloak/data/import
envsubst '${KC_FRONTEND_URL} ${KC_WEB_CLIENT_SECRET} ${KC_STAFF_CLIENT_SECRET} ${KC_SSL_REQUIRED} ${KC_SMTP_HOST} ${KC_SMTP_PORT} ${KC_SMTP_FROM}' \
  < /opt/jdhp/realm-jdhp.template.json > /opt/keycloak/data/import/realm-jdhp.json
exec /opt/keycloak/bin/kc.sh "$@"
