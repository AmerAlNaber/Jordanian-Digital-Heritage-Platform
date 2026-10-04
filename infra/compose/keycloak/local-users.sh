#!/usr/bin/env bash
# Local development only: create one user per role with the password from .env.
# Never run against staging, pilot or production.
set -euo pipefail
: "${KC_DEV_USER_PASSWORD:?set KC_DEV_USER_PASSWORD}"
: "${KEYCLOAK_ADMIN:?}"; : "${KEYCLOAK_ADMIN_PASSWORD:?}"
KC=/opt/keycloak/bin/kcadm.sh
$KC config credentials --server http://localhost:8080/auth --realm master --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD"
for role in member verified_researcher curator reviewer rights_officer platform_admin; do
  email="${role//_/-}@local.test"
  if ! $KC get users -r jdhp -q "email=$email" | grep -q '"id"'; then
    $KC create users -r jdhp -s "username=$email" -s "email=$email" -s enabled=true -s emailVerified=true \
      -s "firstName=${role}" -s "lastName=local" -s 'attributes.phoneNumberVerified=["true"]'
    $KC set-password -r jdhp --username "$email" --new-password "$KC_DEV_USER_PASSWORD"
    $KC add-roles -r jdhp --uusername "$email" --rolename "$role"
  fi
done
echo "local users ready (password from KC_DEV_USER_PASSWORD); staff accounts must enrol OTP on first login"
